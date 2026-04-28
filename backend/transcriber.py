import asyncio
import importlib
import logging
import os
from typing import Any, Optional

from groq_transcriber import format_transcription_markdown


logger = logging.getLogger(__name__)

WHISPER_MODEL_PRESETS = ["tiny", "base", "small", "medium", "large-v3"]


class WhisperDependencyError(Exception):
    """Raised when faster-whisper is unavailable."""


class WhisperLocalTranscriber:
    """Local Faster-Whisper transcription backend."""

    def __init__(self, model_id: str = "base"):
        self.model_id = (model_id or "base").strip()
        self.model = None
        self.last_detected_language = None
        self.runtime = self._detect_runtime()

    @staticmethod
    def dependency_available(importlib_module: Any = importlib) -> bool:
        return importlib_module.util.find_spec("faster_whisper") is not None

    @staticmethod
    def _detect_runtime(importlib_module: Any = importlib) -> str:
        try:
            if importlib_module.util.find_spec("torch") is None:
                return "cpu"
            torch = importlib_module.import_module("torch")
            return "cuda" if getattr(torch.cuda, "is_available", lambda: False)() else "cpu"
        except Exception:
            return "cpu"

    def _load_model(self):
        if self.model is not None:
            return

        if not self.dependency_available():
            raise WhisperDependencyError(
                "faster-whisper is not installed. Install it to use local Whisper transcription."
            )

        logger.info("Loading Faster-Whisper model %s on %s", self.model_id, self.runtime)
        faster_whisper = importlib.import_module("faster_whisper")
        compute_type = "float16" if self.runtime == "cuda" else "int8"
        self.model = faster_whisper.WhisperModel(
            self.model_id,
            device=self.runtime,
            compute_type=compute_type,
        )

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> dict[str, Any]:
        if not os.path.exists(audio_path):
            raise Exception(f"Audio file does not exist: {audio_path}")

        self._load_model()
        logger.info("Starting local Whisper transcription: %s", audio_path)

        def _do_transcribe():
            return self.model.transcribe(
                audio_path,
                language=language or None,
                beam_size=5,
                best_of=5,
                temperature=[0.0, 0.2, 0.4],
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 900,
                    "speech_pad_ms": 300,
                },
                no_speech_threshold=0.7,
                compression_ratio_threshold=2.3,
                log_prob_threshold=-1.0,
                condition_on_previous_text=False,
            )

        segments, info = await asyncio.to_thread(_do_transcribe)

        detected_language = getattr(info, "language", None) or (language or "")
        self.last_detected_language = detected_language
        probability = getattr(info, "language_probability", None)

        raw_segments = []
        for segment in segments:
            raw_segments.append(
                {
                    "start": getattr(segment, "start", None),
                    "end": getattr(segment, "end", None),
                    "text": (getattr(segment, "text", "") or "").strip(),
                }
            )

        markdown = format_transcription_markdown(
            {
                "language": detected_language,
                "language_probability": probability,
                "segments": raw_segments,
            },
            fallback_language=detected_language,
        )

        return {
            "raw": {
                "language": detected_language,
                "language_probability": probability,
                "segments": raw_segments,
            },
            "markdown": markdown,
            "language": detected_language,
            "warnings": [],
            "runtime": self.runtime,
            "timestamps_supported": True,
            "model": self.model_id,
        }

    def get_detected_language(self, transcript_text: Optional[str] = None) -> Optional[str]:
        if self.last_detected_language:
            return self.last_detected_language

        if transcript_text and "**Detected Language:**" in transcript_text:
            for line in transcript_text.splitlines():
                if "**Detected Language:**" in line:
                    return line.split(":", 1)[-1].strip()

        return None


Transcriber = WhisperLocalTranscriber
