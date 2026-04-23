from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import asyncio
import logging
from pathlib import Path
import aiofiles
import uuid
import json
import re
import openai

from video_processor import VideoProcessor
from groq_transcriber import DEFAULT_GROQ_MODEL, GroqTranscriptionError, GroqURLTranscriber
from html_export import render_summary_html
from summarizer import Summarizer
from transcript_formatting import format_transcript_without_timecodes

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI视频转录器", version="1.0.0")

# CORS中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

# 创建临时目录
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# 初始化处理器
video_processor = VideoProcessor()
summarizer = Summarizer()
FORCE_GROQ_TRANSCRIPTION = os.getenv("FORCE_GROQ_TRANSCRIPTION", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# 存储任务状态 - 使用文件持久化
import json
import threading

TASKS_FILE = TEMP_DIR / "tasks.json"
tasks_lock = threading.Lock()

def load_tasks():
    """加载任务状态"""
    try:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_tasks(tasks_data):
    """保存任务状态"""
    try:
        with tasks_lock:
            with open(TASKS_FILE, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存任务状态失败: {e}")

async def broadcast_task_update(task_id: str, task_data: dict):
    """向所有连接的SSE客户端广播任务状态更新"""
    logger.info(f"广播任务更新: {task_id}, 状态: {task_data.get('status')}, 连接数: {len(sse_connections.get(task_id, []))}")
    if task_id in sse_connections:
        connections_to_remove = []
        for queue in sse_connections[task_id]:
            try:
                await queue.put(json.dumps(task_data, ensure_ascii=False))
                logger.debug(f"消息已发送到队列: {task_id}")
            except Exception as e:
                logger.warning(f"发送消息到队列失败: {e}")
                connections_to_remove.append(queue)
        
        # 移除断开的连接
        for queue in connections_to_remove:
            sse_connections[task_id].remove(queue)
        
        # 如果没有连接了，清理该任务的连接列表
        if not sse_connections[task_id]:
            del sse_connections[task_id]

# 启动时加载任务状态
tasks = load_tasks()
# 存储正在处理的URL，防止重复处理
processing_urls = set()
# 存储活跃的任务对象，用于控制和取消
active_tasks = {}
active_summary_tasks = {}
# 存储SSE连接，用于实时推送状态更新
sse_connections = {}

def _sanitize_title_for_filename(title: str) -> str:
    """将视频标题清洗为安全的文件名片段。"""
    if not title:
        return "untitled"
    # 仅保留字母数字、下划线、连字符与空格
    safe = re.sub(r"[^\w\-\s]", "", title)
    # 压缩空白并转为下划线
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    # 最长限制，避免过长文件名问题
    return safe[:80] or "untitled"

def _extract_detected_language(transcript_text: str, fallback: str = "") -> str:
    if not transcript_text:
        return fallback or ""

    for line in transcript_text.splitlines():
        if "**Detected Language:**" in line:
            return line.split(":", 1)[-1].strip()
    return fallback or ""

def _file_name_from_path(value: str) -> str:
    return Path(value).name if value else ""

GROQ_MEDIA_RETRIEVAL_PATTERNS = (
    "failed to retrieve media",
    "received status code: 302",
    "status code: 302",
    "context deadline exceeded",
)


def _is_groq_media_retrieval_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(pattern in message for pattern in GROQ_MEDIA_RETRIEVAL_PATTERNS)


def _format_groq_transcription_error(
    error: Exception,
    retried: bool = False,
    file_fallback_error: Exception | None = None,
) -> str:
    if not _is_groq_media_retrieval_error(error):
        return str(error)

    retry_note = (
        "The app retried with a fresh URL, but Groq still could not fetch it."
        if retried
        else "The app could not fetch the media URL through Groq."
    )
    fallback_note = (
        f" A local file upload fallback also failed: {file_fallback_error}."
        if file_fallback_error
        else ""
    )
    return (
        "Groq could not retrieve the temporary media URL. "
        "YouTube signed media URLs can redirect, expire, or time out from Groq's network. "
        f"{retry_note} Try again, use a video with YouTube subtitles, or use a directly accessible media URL. "
        f"Original Groq error: {error}.{fallback_note}"
    )

@app.get("/")
async def read_root():
    """返回前端页面"""
    return FileResponse(str(PROJECT_ROOT / "static" / "index.html"))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(PROJECT_ROOT / "static" / "favicon.svg"), media_type="image/svg+xml")

@app.post("/api/models")
async def list_models(
    base_url: str = Form(default=""),
    api_key:  str = Form(default=""),
):
    """Proxy: fetch model list from any OpenAI-compatible API."""
    effective_key = api_key or os.getenv("OPENAI_API_KEY", "")
    effective_url = base_url.rstrip("/") or os.getenv("OPENAI_BASE_URL") or None

    if not effective_key:
        raise HTTPException(status_code=400, detail="API key is required")

    try:
        client = openai.OpenAI(api_key=effective_key, base_url=effective_url)
        resp   = await asyncio.to_thread(client.models.list)
        models = [{"id": m.id, "name": getattr(m, "name", m.id)} for m in resp.data]
        # Sort by id for readability
        models.sort(key=lambda x: x["id"])
        return {"data": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/process-video")
async def process_video(
    url: str = Form(...),
    summary_language: str = Form(default="zh"),
    api_key:       str = Form(default=""),
    model_base_url: str = Form(default=""),
    model_id:      str = Form(default=""),
    groq_api_key: str = Form(default=""),
    groq_model: str = Form(default=DEFAULT_GROQ_MODEL),
    groq_language: str = Form(default=""),
    groq_prompt: str = Form(default=""),
    include_timecodes: bool = Form(default=False),
):
    """
    处理视频链接，返回转录任务ID。摘要在单独端点中由用户确认后生成。
    """
    try:
        _ = (summary_language, api_key, model_base_url, model_id)  # accepted for older clients
        # 检查是否已经在处理相同的URL
        if url in processing_urls:
            # 查找现有任务
            for tid, task in tasks.items():
                if task.get("url") == url:
                    return {"task_id": tid, "message": "该视频正在处理中，请等待..."}
            
        # 生成唯一任务ID
        task_id = str(uuid.uuid4())
        
        # 标记URL为正在处理
        processing_urls.add(url)
        
        # 初始化任务状态
        tasks[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理视频...",
            "script": None,
            "transcript": None,
            "transcript_source": None,
            "transcription_source": None,
            "summary": None,
            "summary_status": "idle",
            "summary_progress": 0,
            "summary_path": None,
            "summary_markdown_path": None,
            "summary_html_path": None,
            "error": None,
            "url": url  # 保存URL用于去重
        }
        save_tasks(tasks)
        
        # 创建并跟踪异步任务
        task = asyncio.create_task(
            process_video_task(
                task_id=task_id,
                url=url,
                groq_api_key=groq_api_key,
                groq_model=groq_model,
                groq_language=groq_language,
                groq_prompt=groq_prompt,
                include_timecodes=include_timecodes,
            )
        )
        active_tasks[task_id] = task
        
        return {"task_id": task_id, "message": "任务已创建，正在处理中..."}
        
    except Exception as e:
        logger.error(f"处理视频时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

async def process_video_task(
    task_id: str,
    url: str,
    groq_api_key: str = "",
    groq_model: str = DEFAULT_GROQ_MODEL,
    groq_language: str = "",
    groq_prompt: str = "",
    include_timecodes: bool = False,
    skip_subtitles: bool = FORCE_GROQ_TRANSCRIPTION,
):
    """
    异步处理转录任务。先取字幕；无字幕时只解析音频URL并交给Groq。
    """
    try:
        tasks[task_id].update({
            "status": "processing",
            "progress": 10,
            "message": "正在检测视频字幕..."
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        await asyncio.sleep(0.1)

        if skip_subtitles:
            subtitle_text, sub_title, sub_lang, subtitle_source = None, None, None, None
            tasks[task_id].update({
                "progress": 18,
                "message": "Subtitle stage is temporarily disabled; using Groq transcription..."
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
        else:
            subtitle_result = await video_processor.fetch_subtitles(url, TEMP_DIR)
            if len(subtitle_result) == 3:
                subtitle_text, sub_title, sub_lang = subtitle_result
                subtitle_source = "youtube_manual_subtitles"
            else:
                subtitle_text, sub_title, sub_lang, subtitle_source = subtitle_result

        if subtitle_text:
            video_title = sub_title or "unknown"
            raw_script = subtitle_text
            detected_language = sub_lang or _extract_detected_language(raw_script)
            transcript_source = subtitle_source or "youtube_manual_subtitles"

            tasks[task_id].update({
                "progress": 70,
                "message": f"字幕获取成功（{detected_language or 'unknown'}），正在保存转录文本..."
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])
        else:
            if not groq_api_key.strip():
                raise Exception("未找到YouTube字幕。请在设置中填写Groq API Key，然后重试URL转录。")

            tasks[task_id].update({
                "progress": 25,
                "message": "未找到字幕，正在解析可供Groq读取的音频URL..."
            })
            save_tasks(tasks)
            await broadcast_task_update(task_id, tasks[task_id])

            groq = GroqURLTranscriber(api_key=groq_api_key, model=groq_model)
            groq_result = None
            video_title = "unknown"
            last_media_error = None
            transcript_source = "groq_audio_url"

            for attempt in range(2):
                if attempt:
                    tasks[task_id].update({
                        "progress": 42,
                        "message": "Groq无法读取上一个音频URL，正在刷新URL并重试..."
                    })
                    save_tasks(tasks)
                    await broadcast_task_update(task_id, tasks[task_id])

                audio_info = await video_processor.extract_audio_url(url)
                video_title = audio_info.get("title") or video_title

                tasks[task_id].update({
                    "progress": 45 if attempt == 0 else 55,
                    "message": "音频URL已解析，正在发送给Groq转录..."
                })
                save_tasks(tasks)
                await broadcast_task_update(task_id, tasks[task_id])

                try:
                    groq_result = await groq.transcribe_url(
                        audio_info["audio_url"],
                        language=groq_language.strip(),
                        prompt=groq_prompt.strip(),
                    )
                    break
                except GroqTranscriptionError as e:
                    if _is_groq_media_retrieval_error(e):
                        last_media_error = e
                        if attempt == 0:
                            logger.warning(f"Groq无法读取音频URL，刷新URL后重试: {e}")
                            continue
                        break
                    raise GroqTranscriptionError(
                        _format_groq_transcription_error(e, retried=bool(last_media_error) or attempt > 0)
                    ) from e

            if groq_result is None and last_media_error:
                audio_file = ""
                try:
                    tasks[task_id].update({
                        "progress": 62,
                        "message": "Groq could not fetch the media URL; downloading audio locally for file upload..."
                    })
                    save_tasks(tasks)
                    await broadcast_task_update(task_id, tasks[task_id])

                    if hasattr(video_processor, "download_audio_for_upload"):
                        download_for_upload = video_processor.download_audio_for_upload
                    else:
                        download_for_upload = video_processor.download_and_convert
                    audio_file, downloaded_title = await download_for_upload(url, TEMP_DIR)
                    video_title = downloaded_title or video_title

                    tasks[task_id].update({
                        "progress": 72,
                        "message": "Uploading local audio file to Groq transcription..."
                    })
                    save_tasks(tasks)
                    await broadcast_task_update(task_id, tasks[task_id])

                    groq_result = await groq.transcribe_file(
                        audio_file,
                        language=groq_language.strip(),
                        prompt=groq_prompt.strip(),
                    )
                    transcript_source = "groq_audio_file"
                except Exception as file_error:
                    raise GroqTranscriptionError(
                        _format_groq_transcription_error(
                            last_media_error,
                            retried=True,
                            file_fallback_error=file_error,
                        )
                    ) from file_error
                finally:
                    if audio_file:
                        try:
                            Path(audio_file).unlink(missing_ok=True)
                        except Exception:
                            logger.debug("Could not remove temporary audio file: %s", audio_file)

            if groq_result is None:
                raise GroqTranscriptionError(
                    _format_groq_transcription_error(
                        last_media_error or GroqTranscriptionError("Unknown Groq transcription error"),
                        retried=bool(last_media_error),
                    )
                )

            raw_script = groq_result["markdown"]
            detected_language = groq_result.get("language") or _extract_detected_language(raw_script, groq_language)

        if not include_timecodes:
            raw_script = format_transcript_without_timecodes(raw_script)

        short_id = task_id.replace("-", "")[:6]
        safe_title = _sanitize_title_for_filename(video_title)
        raw_md_filename = f"raw_{safe_title}_{short_id}.md"
        raw_md_path = TEMP_DIR / raw_md_filename
        raw_content = (raw_script or "").strip() + f"\n\nsource: {url}\n"
        async with aiofiles.open(raw_md_path, "w", encoding="utf-8") as f:
            await f.write(raw_content)

        source_labels = {
            "youtube_manual_subtitles": "YouTube manual subtitles",
            "youtube_auto_subtitles": "YouTube automatic subtitles",
            "groq_audio_url": f"Groq URL transcription ({groq_model or DEFAULT_GROQ_MODEL})",
            "groq_audio_file": f"Groq file upload transcription ({groq_model or DEFAULT_GROQ_MODEL})",
        }
        source_label = source_labels.get(transcript_source, transcript_source)
        script_with_title = (
            f"# {video_title}\n\n"
            f"**Transcription Source:** {source_label}\n\n"
            f"{(raw_script or '').strip()}\n\n"
            f"source: {url}\n"
        )

        script_filename = f"transcript_{safe_title}_{short_id}.md"
        script_path = TEMP_DIR / script_filename
        async with aiofiles.open(script_path, "w", encoding="utf-8") as f:
            await f.write(script_with_title)
        
        task_result = {
            "status": "completed",
            "progress": 100,
            "message": "转录完成。确认后可生成AI摘要。",
            "video_title": video_title,
            "script": script_with_title,
            "transcript": script_with_title,
            "summary": None,
            "script_path": str(script_path),
            "raw_script_file": raw_md_filename,
            "summary_path": None,
            "summary_markdown_path": None,
            "summary_html_path": None,
            "summary_status": "idle",
            "summary_progress": 0,
            "short_id": short_id,
            "safe_title": safe_title,
            "detected_language": detected_language,
            "transcript_source": transcript_source,
            "transcription_source": transcript_source,
            "groq_model": groq_model if transcript_source == "groq_audio_url" else None,
        }

        tasks[task_id].update(task_result)
        save_tasks(tasks)
        logger.info(f"任务完成，准备广播最终状态: {task_id}")
        await broadcast_task_update(task_id, tasks[task_id])
        logger.info(f"最终状态已广播: {task_id}")
        
        # 从处理列表中移除URL
        processing_urls.discard(url)
        
        # 从活跃任务列表中移除
        if task_id in active_tasks:
            del active_tasks[task_id]
        
        # 不要立即删除临时文件！保留给用户下载
        # 文件会在一定时间后自动清理或用户手动清理
            
    except GroqTranscriptionError as e:
        logger.error(f"任务 {task_id} Groq转录失败: {str(e)}")
        processing_urls.discard(url)
        if task_id in active_tasks:
            del active_tasks[task_id]
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"Groq转录失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {str(e)}")
        # 从处理列表中移除URL
        processing_urls.discard(url)
        
        # 从活跃任务列表中移除
        if task_id in active_tasks:
            del active_tasks[task_id]
            
        tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "message": f"处理失败: {str(e)}"
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

@app.post("/api/summarize-transcript")
async def summarize_transcript(
    task_id: str = Form(...),
    summary_language: str = Form(default="en"),
    api_key: str = Form(default=""),
    model_base_url: str = Form(default=""),
    model_id: str = Form(default=""),
    output_format: str = Form(default="markdown"),
    summary_prompt: str = Form(default=""),
    reasoning_effort: str = Form(default=""),
):
    """
    Start a summary job only after the user confirms sending the transcript.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_data = tasks[task_id]
    transcript = task_data.get("transcript") or task_data.get("script")
    if not transcript:
        raise HTTPException(status_code=400, detail="该任务还没有可摘要的转录文本")

    normalized_format = (output_format or "markdown").strip().lower()
    if normalized_format not in {"markdown", "html", "both"}:
        raise HTTPException(status_code=400, detail="output_format must be markdown, html, or both")

    normalized_summary_prompt = summary_prompt.strip() if isinstance(summary_prompt, str) else ""
    if len(normalized_summary_prompt) > 4000:
        raise HTTPException(status_code=400, detail="summary_prompt must be 4000 characters or less")

    normalized_reasoning_effort = reasoning_effort.strip().lower() if isinstance(reasoning_effort, str) else ""
    if normalized_reasoning_effort not in {"", "none", "minimal", "low", "medium", "high", "xhigh"}:
        raise HTTPException(status_code=400, detail="reasoning_effort must be none, minimal, low, medium, high, or xhigh")

    if not api_key.strip() and not summarizer.is_available():
        tasks[task_id].update({
            "summary_status": "idle",
            "summary_error": "Summary provider API key is required.",
            "message": "Summary provider API key is required. Configure summary provider settings and try again.",
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
        raise HTTPException(
            status_code=400,
            detail="Summary provider API key is required. Configure summary provider settings and try again.",
        )

    if task_id in active_summary_tasks and not active_summary_tasks[task_id].done():
        return tasks[task_id]

    tasks[task_id].update({
        "summary_status": "processing",
        "summary_progress": 5,
        "summary_error": None,
        "message": "Generating summary...",
        "summary_language": summary_language,
        "summary_model": model_id or None,
        "summary_output_format": normalized_format,
        "summary_prompt": normalized_summary_prompt,
        "summary_reasoning_effort": normalized_reasoning_effort or None,
    })
    save_tasks(tasks)
    await broadcast_task_update(task_id, tasks[task_id])

    task = asyncio.create_task(
        summarize_transcript_task(
            task_id=task_id,
            summary_language=summary_language,
            api_key=api_key,
            model_base_url=model_base_url,
            model_id=model_id,
            output_format=normalized_format,
            summary_prompt=normalized_summary_prompt,
            reasoning_effort=normalized_reasoning_effort,
        )
    )
    active_summary_tasks[task_id] = task

    return tasks[task_id]

async def summarize_transcript_task(
    task_id: str,
    summary_language: str,
    api_key: str,
    model_base_url: str,
    model_id: str,
    output_format: str,
    summary_prompt: str = "",
    reasoning_effort: str = "",
):
    try:
        task_data = tasks[task_id]
        transcript = task_data.get("transcript") or task_data.get("script")
        video_title = task_data.get("video_title") or "Video Summary"

        tasks[task_id].update({
            "summary_status": "processing",
            "summary_progress": 25,
            "message": "Sending transcript to summary provider...",
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        if api_key.strip():
            effective_url = model_base_url.rstrip("/") or None
            request_summarizer = Summarizer(
                api_key=api_key,
                base_url=effective_url,
                model=model_id or None,
                reasoning_effort=reasoning_effort or None,
            )
            logger.info(f"дЅїз”Ёе‰Ќз«ЇжЏђдѕ›зљ„ж‘и¦ЃAPIпјЊbase_url={effective_url}, model={model_id or 'default'}")
        else:
            request_summarizer = summarizer

        summary = await request_summarizer.summarize(
            transcript,
            summary_language,
            video_title,
            custom_prompt=summary_prompt,
        )
        summary_with_source = summary.rstrip() + f"\n\nsource: {task_data.get('url', '')}\n"

        tasks[task_id].update({
            "summary_progress": 80,
            "message": "Saving summary files...",
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

        short_id = task_data.get("short_id") or task_id.replace("-", "")[:6]
        safe_title = task_data.get("safe_title") or _sanitize_title_for_filename(video_title)

        summary_markdown_path = None
        summary_html_path = None

        if output_format in {"markdown", "both"}:
            summary_filename = f"summary_{safe_title}_{short_id}.md"
            summary_markdown_path = TEMP_DIR / summary_filename
            async with aiofiles.open(summary_markdown_path, "w", encoding="utf-8") as f:
                await f.write(summary_with_source)

        if output_format in {"html", "both"}:
            html_filename = f"summary_{safe_title}_{short_id}.html"
            summary_html_path = TEMP_DIR / html_filename
            html_content = render_summary_html(
                title=video_title,
                summary_markdown=summary_with_source,
                source_url=task_data.get("url", ""),
            )
            async with aiofiles.open(summary_html_path, "w", encoding="utf-8") as f:
                await f.write(html_content)

        tasks[task_id].update({
            "summary": summary_with_source,
            "summary_status": "completed",
            "summary_progress": 100,
            "summary_language": summary_language,
            "summary_model": model_id or None,
            "summary_reasoning_effort": reasoning_effort or None,
            "summary_output_format": output_format,
            "summary_path": str(summary_markdown_path) if summary_markdown_path else None,
            "summary_markdown_path": str(summary_markdown_path) if summary_markdown_path else None,
            "summary_html_path": str(summary_html_path) if summary_html_path else None,
            "message": "Files ready.",
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])

    except Exception as e:
        logger.error(f"ж‘и¦Ѓз”џж€ђе¤±иґҐ: {e}")
        tasks[task_id].update({
            "summary_status": "error",
            "summary_error": str(e),
            "message": f"ж‘и¦Ѓз”џж€ђе¤±иґҐ: {e}",
        })
        save_tasks(tasks)
        await broadcast_task_update(task_id, tasks[task_id])
    finally:
        active_summary_tasks.pop(task_id, None)


@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return tasks[task_id]

@app.get("/api/task-stream/{task_id}")
async def task_stream(task_id: str):
    """
    SSE实时任务状态流
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    async def event_generator():
        # 创建任务专用的队列
        queue = asyncio.Queue()
        
        # 将队列添加到连接列表
        if task_id not in sse_connections:
            sse_connections[task_id] = []
        sse_connections[task_id].append(queue)
        
        try:
            # 立即发送当前状态
            current_task = tasks.get(task_id, {})
            yield f"data: {json.dumps(current_task, ensure_ascii=False)}\n\n"
            
            # 持续监听状态更新
            while True:
                try:
                    # 等待状态更新，超时时间30秒发送心跳
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                    
                    # 如果任务完成或失败，结束流
                    task_data = json.loads(data)
                    summary_status = task_data.get("summary_status")
                    if task_data.get("status") == "error":
                        break
                    if summary_status == "processing":
                        continue
                    if summary_status in ["completed", "error"]:
                        break
                    if task_data.get("status") == "completed":
                        break
                        
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                    
        except asyncio.CancelledError:
            logger.info(f"SSE连接被取消: {task_id}")
        except Exception as e:
            logger.error(f"SSE流异常: {e}")
        finally:
            # 清理连接
            if task_id in sse_connections and queue in sse_connections[task_id]:
                sse_connections[task_id].remove(queue)
                if not sse_connections[task_id]:
                    del sse_connections[task_id]
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    直接从temp目录下载文件（简化方案）
    """
    try:
        # 检查文件扩展名安全性
        suffix = Path(filename).suffix.lower()
        if suffix not in {'.md', '.html'}:
            raise HTTPException(status_code=400, detail="仅支持下载.md和.html文件")
        
        # 检查文件名格式（防止路径遍历攻击）
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="文件名格式无效")
            
        file_path = TEMP_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        media_type = "text/html" if suffix == ".html" else "text/markdown"
            
        return FileResponse(
            file_path,
            filename=filename,
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """
    取消并删除任务
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 如果任务还在运行，先取消它
    if task_id in active_tasks:
        task = active_tasks[task_id]
        if not task.done():
            task.cancel()
            logger.info(f"任务 {task_id} 已被取消")
        del active_tasks[task_id]

    if task_id in active_summary_tasks:
        summary_task = active_summary_tasks[task_id]
        if not summary_task.done():
            summary_task.cancel()
            logger.info(f"summary task {task_id} cancelled")
        del active_summary_tasks[task_id]
    
    # 从处理URL列表中移除
    task_url = tasks[task_id].get("url")
    if task_url:
        processing_urls.discard(task_url)
    
    # 删除任务记录
    del tasks[task_id]
    return {"message": "任务已取消并删除"}

@app.get("/api/tasks/active")
async def get_active_tasks():
    """
    获取当前活跃任务列表（用于调试）
    """
    active_count = len(active_tasks)
    summary_count = len(active_summary_tasks)
    processing_count = len(processing_urls)
    return {
        "active_tasks": active_count,
        "active_summary_tasks": summary_count,
        "processing_urls": processing_count,
        "task_ids": list(active_tasks.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
