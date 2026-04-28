# AI Video Transcriber

Fork of [wendy7756/AI-Video-Transcriber](https://github.com/wendy7756/AI-Video-Transcriber)

## What Changed In This Fork

- Windows-first local setup and launcher flow
- Subtitle-first transcription with explicit provider selection
- Groq transcription, local Whisper/Parakeet support, and Groq-to-local fallback
- User-configurable summary provider via OpenAI-compatible APIs
- Additional transcript/summary export and UI workflow improvements

本分支面向 Windows 10 本地运行，不使用 Docker。

## 功能

- YouTube 字幕优先：优先读取手动字幕或自动字幕，不下载视频。
- Groq 转录回退：没有字幕时，用 `yt-dlp` 解析临时音频 URL，并把 URL 发送到 Groq Speech-to-Text。
- 摘要二次确认：转录完成后，用户点击 **Generate Summary** 才会把转录文本发送到摘要模型。
- 导出文件：转录保存为 Markdown，摘要可保存为 Markdown、HTML 或二者同时保存。

## Windows 10 启动

```powershell
cd D:\Projects\AI-Video-Transcriber
.\start_windows.bat
```

手动启动：

```powershell
cd D:\Projects\AI-Video-Transcriber
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python start.py
```

启动后打开：

```text
http://localhost:8001
```

## 使用流程

1. 粘贴 YouTube 视频 URL。
2. 在 **AI Settings** 中填写 Groq API Key；只有视频没有可用字幕时才需要。
3. 如需摘要，填写 OpenAI-compatible 摘要服务的 Base URL、API Key 和模型。
4. 点击 **Transcribe**。
5. 查看转录文本。
6. 选择 Markdown、HTML 或 Markdown + HTML，然后点击 **Generate Summary**。
7. 下载转录和摘要文件。

## 配置

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `HOST` | 服务监听地址 | `0.0.0.0` |
| `PORT` | 服务端口 | `8001` |
| `OPENAI_API_KEY` | 摘要服务默认 API Key，也可在页面中填写 | 空 |
| `OPENAI_BASE_URL` | 摘要服务默认 Base URL | `https://api.openai.com/v1` |

## 说明

- 本分支不依赖本地 Faster-Whisper。
- 本分支不要求 FFmpeg。
- Groq 回退依赖临时音频 URL；如果 URL 过期或 Groq 无法读取，请重新点击转录生成新的 URL。
