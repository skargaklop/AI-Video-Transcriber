import os
import re
import shutil
import subprocess
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
import yt_dlp
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SUBTITLE_LANGUAGE_PRIORITY = ["en", "en-orig", "zh-Hans", "zh-Hant", "zh", "ru", "ja", "ko", "fr", "de", "es"]
WORD_RE = re.compile(r"\S+")


def ensure_ffmpeg_binary() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "imageio-ffmpeg>=0.5.1"],
        check=True,
        capture_output=True,
        text=True,
    )
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration_with_ffmpeg(audio_file: str, ffmpeg_path: str) -> float:
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-i", audio_file, "-f", "null", "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        output = f"{proc.stdout}\n{proc.stderr}"
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if not match:
            return 0.0
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0.0


def _normalize_overlap_token(token: str) -> str:
    return re.sub(r"^\W+|\W+$", "", token, flags=re.UNICODE).casefold()


def _tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [
        (_normalize_overlap_token(match.group(0)), match.start(), match.end())
        for match in WORD_RE.finditer(text)
    ]


def remove_leading_text_overlap(previous_text: str, current_text: str, min_overlap_tokens: int = 3) -> str:
    previous_tokens = [token for token, _, _ in _tokenize_with_spans(previous_text) if token]
    current_spans = [(token, start, end) for token, start, end in _tokenize_with_spans(current_text) if token]
    current_tokens = [token for token, _, _ in current_spans]

    max_overlap = min(len(previous_tokens), len(current_tokens))
    for overlap_size in range(max_overlap, min_overlap_tokens - 1, -1):
        if previous_tokens[-overlap_size:] == current_tokens[:overlap_size]:
            cut_at = current_spans[overlap_size - 1][2]
            return current_text[cut_at:].lstrip(" ,.;:!?-–—")

    return current_text


def _caption_entry_is_translated(entry: dict[str, Any]) -> bool:
    url = str(entry.get("url") or "")
    if not url:
        return False
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return "tlang" in query


def select_subtitle_language(captions: dict[str, list[dict[str, Any]]], prefer_original: bool = False) -> Optional[str]:
    languages = [lang for lang in captions if not lang.startswith("live_chat")]
    if not languages:
        return None

    if prefer_original:
        original_languages = [
            lang
            for lang in languages
            if any(not _caption_entry_is_translated(entry) for entry in captions.get(lang, []))
        ]
        if original_languages:
            return next(
                (lang for lang in SUBTITLE_LANGUAGE_PRIORITY if lang in original_languages),
                original_languages[0],
            )

    return next(
        (lang for lang in SUBTITLE_LANGUAGE_PRIORITY if lang in languages),
        languages[0],
    )


def _audio_format_score(fmt: dict[str, Any]) -> int:
    if not fmt.get("url"):
        return -1

    protocol = str(fmt.get("protocol") or "")
    if protocol and not protocol.startswith(("http", "https")):
        return -1

    score = 0
    if fmt.get("acodec") and fmt.get("acodec") != "none":
        score += 100
    if fmt.get("vcodec") == "none":
        score += 40

    ext = str(fmt.get("ext") or "").lower()
    if ext in {"m4a", "mp4"}:
        score += 30
    elif ext in {"webm", "mp3", "ogg", "opus"}:
        score += 15

    abr = fmt.get("abr") or fmt.get("tbr") or 0
    try:
        score += min(int(float(abr)), 320)
    except (TypeError, ValueError):
        pass

    return score


def select_audio_format(formats: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    candidates = [(fmt, _audio_format_score(fmt)) for fmt in formats]
    candidates = [(fmt, score) for fmt, score in candidates if score >= 0]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[0]


def _timecode_to_seconds(timecode: str) -> float:
    parts = str(timecode).split(":")
    if not parts:
        return 0
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return 0
    if len(values) == 3:
        return values[0] * 3600 + values[1] * 60 + values[2]
    if len(values) == 2:
        return values[0] * 60 + values[1]
    return values[0]


def _normalize_chapters(chapters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = []
    for chapter in chapters or []:
        title = str(chapter.get("title") or "").strip()
        if not title:
            continue
        try:
            start = float(chapter.get("start_time") or 0)
        except (TypeError, ValueError):
            start = 0
        normalized.append({"start_time": start, "title": title})
    return sorted(normalized, key=lambda item: item["start_time"])


def resolve_media_redirect_url(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    opener: Any = None,
) -> str:
    """
    Follow media redirects locally before giving the URL to Groq.

    Groq may reject YouTube/Googlevideo URLs that respond with a bare 302,
    while Python's opener follows that redirect and exposes the final URL.
    """
    opener = opener or urllib.request.build_opener()
    request_headers = dict(headers or {})
    if "User-Agent" not in request_headers:
        request_headers["User-Agent"] = "AI-Video-Transcriber/1.0"

    def open_url(method: str) -> str:
        extra_headers = dict(request_headers)
        if method == "GET":
            extra_headers.setdefault("Range", "bytes=0-0")
        request = urllib.request.Request(url, headers=extra_headers, method=method)
        with opener.open(request, timeout=timeout) as response:
            return response.geturl()

    try:
        return open_url("HEAD")
    except urllib.error.HTTPError as exc:
        if exc.code not in {403, 405, 501}:
            raise
        return open_url("GET")


class VideoProcessor:
    """视频处理器，使用yt-dlp获取字幕和直接音频URL。"""
    
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
    
    async def fetch_subtitles(self, url: str, output_dir: Path) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        先尝试从平台获取字幕文本，比下载音频快得多。

        Returns:
            (subtitle_markdown, video_title, language_code)
            subtitle_markdown 为 None 表示无可用字幕。
        """
        import asyncio

        output_dir.mkdir(exist_ok=True)
        unique_id = str(uuid.uuid4())[:8]
        sub_dir = output_dir / f"subs_{unique_id}"

        try:
            # 1. 快速探测：获取视频信息和字幕可用性，不下载任何内容
            check_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(check_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, False)

            video_title = info.get("title", "unknown")
            manual_subs: dict = info.get("subtitles") or {}
            auto_caps: dict = info.get("automatic_captions") or {}

            # 过滤掉 live_chat 等非语音轨道
            manual_langs = [k for k in manual_subs if not k.startswith("live_chat")]
            auto_langs = [k for k in auto_caps if not k.startswith("live_chat")]

            if not manual_langs and not auto_langs:
                logger.info(f"视频无可用字幕: {url}")
                return None, video_title, None, None

            # 优先手动字幕，其次自动字幕
            prefer_manual = bool(manual_langs)
            candidate_langs = manual_langs if prefer_manual else auto_langs
            transcript_source = "youtube_manual_subtitles" if prefer_manual else "youtube_auto_subtitles"

            # 按优先级选语言：英语 > 简体中文 > 繁体中文 > 其他（取第一个）
            prefer_lang = select_subtitle_language(
                manual_subs if prefer_manual else auto_caps,
                prefer_original=not prefer_manual,
            ) or candidate_langs[0]
            logger.info(
                f"发现{'手动' if prefer_manual else '自动'}字幕，选用语言: {prefer_lang}"
                f"（候选 {len(candidate_langs)} 种）"
            )

            # 2. 仅下载字幕，跳过音视频
            sub_dir.mkdir(exist_ok=True)
            dl_opts = {
                "writesubtitles": prefer_manual,
                "writeautomaticsub": not prefer_manual,
                "subtitlesformat": "vtt/srt/best",
                "subtitleslangs": [prefer_lang],
                "skip_download": True,
                "outtmpl": str(sub_dir / "sub.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])

            # 3. 查找下载的字幕文件
            sub_files = list(sub_dir.glob("*.vtt")) + list(sub_dir.glob("*.srt"))
            if not sub_files:
                logger.warning("字幕下载后未找到文件，回退至Groq URL转录")
                return None, video_title, None, None

            sub_file = sub_files[0]

            # 从文件名提取语言代码 (e.g. sub.en.vtt → en)
            stem_parts = sub_file.stem.split(".")
            file_lang = stem_parts[-1] if len(stem_parts) > 1 else prefer_lang

            # 4. 解析字幕文件
            if sub_file.suffix == ".vtt":
                entries = self._parse_vtt(str(sub_file))
            else:
                entries = self._parse_srt(str(sub_file))

            if not entries:
                logger.warning("字幕解析结果为空，回退至Groq URL转录")
                return None, video_title, None, None

            # 5. 格式化为与 Whisper 输出兼容的 Markdown
            formatted = self._format_subtitle_entries(entries, file_lang, chapters=info.get("chapters") or [])
            logger.info(f"字幕获取成功: lang={file_lang}, {len(entries)} 条目")
            return formatted, video_title, file_lang, transcript_source

        except Exception as e:
            logger.warning(f"字幕获取失败（将回退至Groq URL转录）: {e}")
            return None, None, None, None
        finally:
            if sub_dir.exists():
                try:
                    shutil.rmtree(str(sub_dir))
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 字幕解析辅助方法
    # ------------------------------------------------------------------

    def _parse_vtt(self, filepath: str) -> list:
        """解析 WebVTT 字幕文件，返回去重后的条目列表。

        特别处理 YouTube 自动字幕的「滚动追加」格式：
        同一句话会被分成多个 cue 逐字追加，只保留每组的「最终版本」。
        """
        raw_entries = []
        seen_texts: set = set()

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"读取 VTT 文件失败: {e}")
            return []

        # 移除 WEBVTT 文件头，按空行分割 cue 块
        content = re.sub(r"^WEBVTT[^\n]*\n", "", content)
        blocks = re.split(r"\n{2,}", content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            timing_idx = next((i for i, l in enumerate(lines) if "-->" in l), -1)
            if timing_idx < 0:
                continue

            timing_line = lines[timing_idx]
            text_lines = lines[timing_idx + 1:]

            match = re.match(
                r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-->\s*"
                r"(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)",
                timing_line,
            )
            if not match:
                continue

            start_str = self._normalize_time(match.group(1))
            end_str = self._normalize_time(match.group(2))

            raw_text = " ".join(text_lines)
            # 去除 HTML / VTT 内联标签（包括 YouTube 逐字时间码标签）
            text = re.sub(r"<[^>]+>", "", raw_text)
            text = (
                text.replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&nbsp;", " ")
                    .replace("&#39;", "'")
                    .replace("&quot;", '"')
                    .strip()
            )
            # 合并行内多余空白
            text = re.sub(r"\s+", " ", text).strip()

            if not text or text in seen_texts:
                continue

            seen_texts.add(text)
            raw_entries.append({"start": start_str, "end": end_str, "text": text})

        # ── 二次去重：过滤 YouTube「滚动追加」的中间状态 ──────────────────
        # 若条目 i 的文本是条目 i+1 文本的起始子串，则条目 i 是中间状态，丢弃。
        # 同时丢弃纯空白/单字符的噪音条目。
        if not raw_entries:
            return []

        entries = []
        for i, entry in enumerate(raw_entries):
            text = entry["text"]
            if len(text) < 2:
                continue
            # 检查后续若干条是否以当前文本开头（滚动追加的特征）
            is_intermediate = False
            for j in range(i + 1, min(i + 4, len(raw_entries))):
                next_text = raw_entries[j]["text"]
                if next_text.startswith(text) and len(next_text) > len(text):
                    is_intermediate = True
                    break
            if not is_intermediate:
                entries.append(entry)

        return entries

    def _parse_srt(self, filepath: str) -> list:
        """解析 SRT 字幕文件，返回去重后的条目列表。"""
        entries = []
        seen_texts: set = set()

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"读取 SRT 文件失败: {e}")
            return []

        blocks = re.split(r"\n{2,}", content.strip())

        for block in blocks:
            lines = block.strip().split("\n")
            timing_idx = next((i for i, l in enumerate(lines) if "-->" in l), -1)
            if timing_idx < 0:
                continue

            timing_line = lines[timing_idx]
            text_lines = lines[timing_idx + 1:]

            match = re.match(
                r"(\d{1,2}:\d{2}:\d{2}[.,]\d+)\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d+)",
                timing_line,
            )
            if not match:
                continue

            start_str = self._normalize_time(match.group(1))
            end_str = self._normalize_time(match.group(2))

            text = " ".join(text_lines)
            text = re.sub(r"<[^>]+>", "", text).strip()

            if not text or text in seen_texts:
                continue

            seen_texts.add(text)
            entries.append({"start": start_str, "end": end_str, "text": text})

        return entries

    def _normalize_time(self, time_str: str) -> str:
        """将 HH:MM:SS.mmm 或 MM:SS.mmm 统一转为 MM:SS 格式。"""
        time_str = re.sub(r"[.,]\d+$", "", time_str)
        parts = time_str.split(":")
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{h * 60 + m:02d}:{s:02d}"
        elif len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return f"{m:02d}:{s:02d}"
        return time_str

    def _format_subtitle_entries(self, entries: list, language: str, chapters: list[dict[str, Any]] | None = None) -> str:
        """将字幕条目格式化为与 Whisper 输出兼容的 Markdown，供下游管道直接使用。"""
        lines = [
            "# Video Transcription",
            "",
            f"**Detected Language:** {language}",
            "**Language Probability:** 1.00",
            "",
            "## Transcription Content",
            "",
        ]
        previous_text = ""
        normalized_chapters = _normalize_chapters(chapters)
        chapter_index = 0
        for entry in entries:
            entry_start = _timecode_to_seconds(entry.get("start", "0"))
            while chapter_index < len(normalized_chapters) and normalized_chapters[chapter_index]["start_time"] <= entry_start:
                lines.append(f"## {normalized_chapters[chapter_index]['title']}")
                lines.append("")
                chapter_index += 1

            entry_text = remove_leading_text_overlap(previous_text, entry["text"])
            if not entry_text:
                previous_text = entry["text"]
                continue
            lines.append(f"**[{entry['start']} - {entry['end']}]**")
            lines.append("")
            lines.append(entry_text)
            lines.append("")
            previous_text = entry["text"]
        return "\n".join(lines)

    async def extract_audio_url(self, url: str) -> dict[str, Any]:
        """
        Resolve a direct audio URL with yt-dlp without downloading media.
        """
        import asyncio

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, False)
        except Exception as e:
            logger.error(f"获取音频URL失败: {e}")
            raise Exception(f"无法解析视频音频URL: {e}") from e

        selected = None
        if info.get("url") and _audio_format_score(info) >= 0:
            selected = info
        else:
            selected = select_audio_format(info.get("formats") or [])

        audio_url = ""
        http_headers = {}
        if selected and selected.get("url"):
            audio_url = selected["url"]
            http_headers = selected.get("http_headers") or info.get("http_headers") or {}
            try:
                resolved_audio_url = await asyncio.to_thread(
                    resolve_media_redirect_url,
                    audio_url,
                    http_headers,
                )
                if resolved_audio_url != audio_url:
                    logger.info("Resolved audio URL redirect: %s -> %s", audio_url[:80], resolved_audio_url[:80])
                audio_url = resolved_audio_url
            except Exception as e:
                logger.warning("Audio URL redirect resolution failed; using original yt-dlp URL: %s", e)

        if not selected or not selected.get("url"):
            raise Exception("未找到可供Groq读取的直接音频URL")

        logger.info(
            "已解析直接音频URL: title=%s format=%s ext=%s",
            info.get("title", "unknown"),
            selected.get("format_id", "unknown"),
            selected.get("ext", "unknown"),
        )

        return {
            "title": info.get("title", "unknown"),
            "duration": info.get("duration"),
            "audio_url": audio_url,
            "format_id": selected.get("format_id"),
            "format_note": selected.get("format_note"),
            "ext": selected.get("ext"),
            "protocol": selected.get("protocol"),
            "http_headers": http_headers,
        }

    async def download_and_convert(self, url: str, output_dir: Path) -> tuple[str, str]:
        """
        Download the best available audio track and normalize it to mono 16 kHz M4A.
        """
        try:
            output_dir.mkdir(exist_ok=True)

            unique_id = str(uuid.uuid4())[:8]
            output_template = str(output_dir / f"audio_{unique_id}.%(ext)s")

            ydl_opts = self.ydl_opts.copy()
            ydl_opts['outtmpl'] = output_template

            logger.info("Downloading audio for local transcription: %s", url)

            import asyncio
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, False)
                video_title = info.get('title', 'unknown')
                expected_duration = info.get('duration') or 0
                logger.info("Downloaded video info: %s", video_title)
                await asyncio.to_thread(ydl.download, [url])

            source_audio_file = ''
            for ext in ['m4a', 'webm', 'mp4', 'mp3', 'wav', 'opus', 'ogg']:
                potential_file = str(output_dir / f"audio_{unique_id}.{ext}")
                if os.path.exists(potential_file):
                    source_audio_file = potential_file
                    break
            if not source_audio_file:
                raise Exception('Audio file was not downloaded')

            ffmpeg_path = ensure_ffmpeg_binary()
            audio_file = str(output_dir / f"audio_{unique_id}.m4a")
            convert_cmd = [
                ffmpeg_path,
                '-y',
                '-i', source_audio_file,
                '-vn',
                '-ac', '1',
                '-ar', '16000',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                audio_file,
            ]
            subprocess.run(convert_cmd, check=True, capture_output=True, text=True)

            actual_duration = probe_duration_with_ffmpeg(audio_file, ffmpeg_path)
            if expected_duration and actual_duration and abs(actual_duration - expected_duration) / expected_duration > 0.1:
                logger.warning(
                    "Audio duration mismatch detected (expected %.2fs, actual %.2fs), repackaging output",
                    expected_duration,
                    actual_duration,
                )
                fixed_path = str(output_dir / f"audio_{unique_id}_fixed.m4a")
                fix_cmd = [
                    ffmpeg_path,
                    '-y',
                    '-i', audio_file,
                    '-vn',
                    '-c:a', 'aac',
                    '-b:a', '160k',
                    '-movflags', '+faststart',
                    fixed_path,
                ]
                subprocess.run(fix_cmd, check=True, capture_output=True, text=True)
                audio_file = fixed_path

            if source_audio_file != audio_file and os.path.exists(source_audio_file):
                try:
                    os.remove(source_audio_file)
                except OSError:
                    logger.debug('Could not remove source audio file: %s', source_audio_file)

            logger.info("Normalized local transcription audio saved: %s", audio_file)
            return audio_file, video_title

        except Exception as e:
            logger.error("Audio download/conversion failed: %s", e)
            raise Exception(f"Audio download/conversion failed: {e}") from e

    async def download_audio_for_upload(self, url: str, output_dir: Path) -> tuple[str, str]:
        """
        Download the original audio container for Groq file upload.

        This path intentionally avoids ffmpeg postprocessing. It is used only
        when Groq cannot fetch a temporary remote media URL itself.
        """
        import asyncio

        output_dir.mkdir(exist_ok=True)
        unique_id = str(uuid.uuid4())[:8]
        output_template = str(output_dir / f"upload_audio_{unique_id}.%(ext)s")
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, False)
                video_title = info.get("title", "unknown")
                await asyncio.to_thread(ydl.download, [url])

            candidates = list(output_dir.glob(f"upload_audio_{unique_id}.*"))
            if not candidates:
                raise Exception("未找到下载的音频文件")

            audio_file = str(candidates[0])
            logger.info("Audio file downloaded for Groq upload: %s", audio_file)
            return audio_file, video_title
        except Exception as e:
            logger.error("下载音频文件失败: %s", e)
            raise Exception(f"下载音频文件失败: {e}") from e
    
    def get_video_info(self, url: str) -> dict:
        """
        获取视频信息
        
        Args:
            url: 视频链接
            
        Returns:
            视频信息字典
        """
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                }
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            raise Exception(f"获取视频信息失败: {str(e)}")
