import asyncio
import importlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

from groq_transcriber import format_transcription_markdown, format_seconds


logger = logging.getLogger(__name__)

PARAKEET_MODEL_PRESETS = [
    "nvidia/parakeet-tdt-0.6b-v3",
    "nvidia/parakeet-tdt-0.6b-v2",
]


class ParakeetDependencyError(Exception):
    """Raised when NeMo / torch are unavailable."""


class ParakeetLocalTranscriber:
    """Best-effort local NVIDIA Parakeet transcription backend."""

    def __init__(self, model_id: str = PARAKEET_MODEL_PRESETS[0]):
        self.model_id = (model_id or PARAKEET_MODEL_PRESETS[0]).strip()
        self.model = None
        self.runtime = self._detect_runtime()

    @staticmethod
    def dependency_available(importlib_module: Any = importlib) -> bool:
        return (
            importlib_module.util.find_spec("torch") is not None
            and importlib_module.util.find_spec("nemo") is not None
        )

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
            raise ParakeetDependencyError(
                "NVIDIA Parakeet dependencies are not installed. Install torch and NeMo ASR to use it."
            )

        torch = importlib.import_module("torch")
        nemo_models = importlib.import_module("nemo.collections.asr.models")
        asr_model_cls = getattr(nemo_models, "ASRModel")
        self.model = asr_model_cls.from_pretrained(model_name=self.model_id)
        if hasattr(self.model, "to"):
            self.model = self.model.to("cuda" if self.runtime == "cuda" else "cpu")
        if hasattr(self.model, "eval"):
            self.model.eval()
        if self.runtime == "cuda" and hasattr(torch, "set_grad_enabled"):
            torch.set_grad_enabled(False)

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> dict[str, Any]:
        if not os.path.exists(audio_path):
            raise Exception(f"Audio file does not exist: {audio_path}")

        self._load_model()
        warnings = []
        if self.runtime == "cpu":
            warnings.append("Parakeet is running on CPU and may be slow.")

        def _do_transcribe():
            if hasattr(self.model, "transcribe"):
                try:
                    return self.model.transcribe([audio_path], timestamps=True)
                except TypeError:
                    return self.model.transcribe([audio_path])
                except Exception:
                    return self.model.transcribe([audio_path])
            raise Exception("Loaded Parakeet model does not expose a transcribe() method")

        result = await asyncio.to_thread(_do_transcribe)
        normalized = self._normalize_result(result)
        warnings.extend(normalized["warnings"])

        markdown = format_transcription_markdown(
            normalized["raw"],
            fallback_language=normalized["language"] or (language or ""),
        )

        return {
            "raw": normalized["raw"],
            "markdown": markdown,
            "language": normalized["language"] or (language or ""),
            "warnings": warnings,
            "runtime": self.runtime,
            "timestamps_supported": normalized["timestamps_supported"],
            "model": self.model_id,
        }

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        warnings: list[str] = []
        language = ""
        timestamps_supported = False
        raw_segments = []
        text_parts = []

        if isinstance(result, tuple):
            transcript_items = result[0]
        else:
            transcript_items = result

        if isinstance(transcript_items, list) and transcript_items:
            first = transcript_items[0]
            if isinstance(first, dict):
                language = str(first.get("language") or "")
                if "text" in first and "start" in first and "end" in first:
                    timestamps_supported = True
                    for item in transcript_items:
                        raw_segments.append(
                            {
                                "start": item.get("start"),
                                "end": item.get("end"),
                                "text": str(item.get("text") or "").strip(),
                            }
                        )
                else:
                    text_parts = [str(item.get("text") or item.get("pred_text") or "").strip() for item in transcript_items]
            elif isinstance(first, str):
                text_parts = [part.strip() for part in transcript_items if str(part).strip()]

        if not raw_segments and not text_parts and isinstance(transcript_items, str):
            text_parts = [transcript_items.strip()]

        if not raw_segments and not text_parts and hasattr(transcript_items, "text"):
            text_parts = [str(getattr(transcript_items, "text") or "").strip()]

        if not raw_segments:
            warnings.append("This local model did not return timestamps; transcript was saved without timecodes.")

        raw: dict[str, Any] = {"language": language}
        if raw_segments:
            raw["segments"] = raw_segments
        else:
            raw["text"] = "\n\n".join([part for part in text_parts if part])

        return {
            "raw": raw,
            "language": language,
            "timestamps_supported": bool(raw_segments),
            "warnings": warnings,
        }
