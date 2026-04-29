import asyncio
import json
import logging
import mimetypes
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTIONS_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3-turbo"


class GroqTranscriptionError(Exception):
    """Raised when Groq URL transcription fails."""


@dataclass(frozen=True)
class MultipartFile:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


def format_seconds(seconds: float | int | None) -> str:
    if seconds is None:
        return "00:00"

    if isinstance(seconds, str):
        text = seconds.strip()
        if not text:
            return "00:00"
        if ":" in text:
            try:
                parts = [float(part) for part in text.split(":")]
            except ValueError:
                return "00:00"
            total = 0.0
            for part in parts:
                total = total * 60 + part
            seconds = total
        else:
            seconds = text

    total = int(float(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def prepare_groq_payload(
    audio_url: str,
    model: str = DEFAULT_GROQ_MODEL,
    language: str = "",
    prompt: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model or DEFAULT_GROQ_MODEL,
        "response_format": "verbose_json",
        "temperature": "0",
        "timestamp_granularities[]": ["segment"],
    }
    if audio_url:
        payload["url"] = audio_url
    normalized_language = language.strip()
    if normalized_language.lower() in {"auto", "auto-detect", "autodetect", "detect"}:
        normalized_language = ""
    if normalized_language:
        payload["language"] = normalized_language
    if prompt:
        payload["prompt"] = prompt.strip()
    return payload


def prepare_groq_file_payload(
    audio_file: str | Path,
    model: str = DEFAULT_GROQ_MODEL,
    language: str = "",
    prompt: str = "",
) -> dict[str, Any]:
    path = Path(audio_file)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = prepare_groq_payload(
        audio_url="",
        model=model,
        language=language,
        prompt=prompt,
    )
    payload["file"] = MultipartFile(
        filename=path.name,
        content=path.read_bytes(),
        content_type=content_type,
    )
    return payload


def build_multipart_form_data(payload: dict[str, Any], boundary: str | None = None) -> tuple[bytes, str]:
    boundary = boundary or f"----AIVideoTranscriber{uuid.uuid4().hex}"
    body_parts: list[bytes] = []

    for name, value in payload.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
            if isinstance(item, MultipartFile):
                body_parts.append(
                    f'Content-Disposition: form-data; name="{name}"; filename="{item.filename}"\r\n'.encode("utf-8")
                )
                body_parts.append(f"Content-Type: {item.content_type}\r\n\r\n".encode("utf-8"))
                body_parts.append(item.content)
            else:
                body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
                body_parts.append(str(item).encode("utf-8"))
            body_parts.append(b"\r\n")

    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body_parts), f"multipart/form-data; boundary={boundary}"


def format_transcription_markdown(data: Any, fallback_language: str = "") -> str:
    language = fallback_language or ""
    probability = ""
    text = ""
    segments: list[dict[str, Any]] = []

    if isinstance(data, str):
        text = data.strip()
    elif isinstance(data, dict):
        language = str(data.get("language") or fallback_language or "")
        probability_value = data.get("language_probability")
        if probability_value is not None:
            probability = f"{float(probability_value):.2f}"
        text = str(data.get("text") or "").strip()
        raw_segments = data.get("segments") or []
        if isinstance(raw_segments, list):
            segments = [segment for segment in raw_segments if isinstance(segment, dict)]

    lines = [
        "# Video Transcription",
        "",
        f"**Detected Language:** {language or 'unknown'}",
    ]
    if probability:
        lines.append(f"**Language Probability:** {probability}")
    lines.extend(["", "## Transcription Content", ""])

    if segments:
        for segment in segments:
            segment_text = str(segment.get("text") or "").strip()
            if not segment_text:
                continue
            start_time = format_seconds(segment.get("start"))
            end_time = format_seconds(segment.get("end"))
            lines.append(f"**[{start_time} - {end_time}]**")
            lines.append("")
            lines.append(segment_text)
            lines.append("")
    elif text:
        lines.append(text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


class GroqURLTranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GROQ_MODEL,
        endpoint: str = GROQ_TRANSCRIPTIONS_ENDPOINT,
        timeout: int = 180,
    ):
        self.api_key = api_key.strip()
        self.model = model or DEFAULT_GROQ_MODEL
        self.endpoint = endpoint
        self.timeout = timeout

        if not self.api_key:
            raise GroqTranscriptionError("Groq API key is required when no subtitles are available.")

    async def transcribe_url(
        self,
        audio_url: str,
        language: str = "",
        prompt: str = "",
    ) -> dict[str, Any]:
        payload = prepare_groq_payload(
            audio_url=audio_url,
            model=self.model,
            language=language,
            prompt=prompt,
        )
        response = await asyncio.to_thread(self._post, payload)
        markdown = format_transcription_markdown(response, fallback_language=language)
        detected_language = ""
        if isinstance(response, dict):
            detected_language = str(response.get("language") or language or "")

        return {
            "raw": response,
            "markdown": markdown,
            "language": detected_language,
            "model": self.model,
        }

    async def transcribe_file(
        self,
        audio_file: str | Path,
        language: str = "",
        prompt: str = "",
    ) -> dict[str, Any]:
        payload = prepare_groq_file_payload(
            audio_file=audio_file,
            model=self.model,
            language=language,
            prompt=prompt,
        )
        response = await asyncio.to_thread(self._post, payload)
        markdown = format_transcription_markdown(response, fallback_language=language)
        detected_language = ""
        if isinstance(response, dict):
            detected_language = str(response.get("language") or language or "")

        return {
            "raw": response,
            "markdown": markdown,
            "language": detected_language,
            "model": self.model,
        }

    def _post(self, payload: dict[str, Any]) -> Any:
        encoded, content_type = build_multipart_form_data(payload)
        request = urllib.request.Request(
            self.endpoint,
            data=encoded,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
                "User-Agent": "AI-Video-Transcriber/1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GroqTranscriptionError(self._extract_error(body) or f"Groq API error: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise GroqTranscriptionError(f"Groq API request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Groq response was not JSON; treating it as plain text.")
            return body

    @staticmethod
    def _extract_error(body: str) -> str:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body[:500]

        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
        return str(data)[:500]
