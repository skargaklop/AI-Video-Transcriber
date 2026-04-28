import asyncio
import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from groq_transcriber import MultipartFile, build_multipart_form_data, format_transcription_markdown


class LocalAPITranscriptionError(Exception):
    """Raised when a local API transcription request fails."""


class LocalAPITranscriber:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        endpoint_path: str = "/audio/transcriptions",
        timeout: int = 300,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.api_key = (api_key or "").strip()
        self.endpoint_path = endpoint_path
        self.timeout = timeout

        if not self.base_url:
            raise LocalAPITranscriptionError("Local API base URL is required for local_api transcription.")
        if not self.model:
            raise LocalAPITranscriptionError("Local API model is required for local_api transcription.")

    async def transcribe_file(
        self,
        audio_file: str | Path,
        language: str = "",
        prompt: str = "",
    ) -> dict[str, Any]:
        payload = self._prepare_payload(audio_file, language=language, prompt=prompt)
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

    def _prepare_payload(self, audio_file: str | Path, language: str = "", prompt: str = "") -> dict[str, Any]:
        path = Path(audio_file)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        payload: dict[str, Any] = {
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": "0",
            "file": MultipartFile(
                filename=path.name,
                content=path.read_bytes(),
                content_type=content_type,
            ),
        }
        normalized_language = (language or "").strip()
        if normalized_language.lower() not in {"", "auto", "auto-detect", "autodetect", "detect"}:
            payload["language"] = normalized_language
        if prompt:
            payload["prompt"] = prompt.strip()
        return payload

    def _post(self, payload: dict[str, Any]) -> Any:
        encoded, content_type = build_multipart_form_data(payload, boundary=f"----LocalAPI{uuid.uuid4().hex}")
        headers = {
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "AI-Video-Transcriber/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}{self.endpoint_path}",
            data=encoded,
            method="POST",
            headers=headers,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LocalAPITranscriptionError(self._extract_error(body) or f"Local API error: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise LocalAPITranscriptionError(f"Local API request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError:
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
