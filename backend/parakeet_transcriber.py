import asyncio
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional

from groq_transcriber import format_seconds, format_transcription_markdown


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARAKEET_MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "onnx_asr"
PARAKEET_MODEL_NAME_MAP = {
    "nvidia/parakeet-tdt-0.6b-v3": "nemo-parakeet-tdt-0.6b-v3",
    "nvidia/parakeet-tdt-0.6b-v2": "nemo-parakeet-tdt-0.6b-v2",
}
PARAKEET_MODEL_PRESETS = list(PARAKEET_MODEL_NAME_MAP.keys())


class ParakeetDependencyError(Exception):
    """Raised when ONNX ASR dependencies are unavailable."""


class ParakeetLocalTranscriber:
    """Local Parakeet transcription backend backed by onnx-asr."""

    def __init__(self, model_id: str = PARAKEET_MODEL_PRESETS[0]):
        self.model_id = (model_id or PARAKEET_MODEL_PRESETS[0]).strip()
        self.runtime = self._detect_runtime()
        self.model = None
        self.vad_enabled = False
        self.timestamps_enabled = False

    @staticmethod
    def dependency_available(importlib_module: Any = importlib) -> bool:
        return (
            importlib_module.util.find_spec("onnx_asr") is not None
            and importlib_module.util.find_spec("onnxruntime") is not None
        )

    @staticmethod
    def _detect_runtime(importlib_module: Any = importlib) -> str:
        try:
            if importlib_module.util.find_spec("onnxruntime") is not None:
                onnxruntime = importlib_module.import_module("onnxruntime")
                providers = set(getattr(onnxruntime, "get_available_providers", lambda: [])())
                accelerated = {
                    "CUDAExecutionProvider",
                    "TensorrtExecutionProvider",
                    "DmlExecutionProvider",
                    "ROCMExecutionProvider",
                }
                if providers.intersection(accelerated):
                    return "cuda"
        except Exception:
            logger.debug("Could not inspect onnxruntime providers", exc_info=True)
        try:
            if importlib_module.util.find_spec("torch") is None:
                return "cpu"
            torch = importlib_module.import_module("torch")
            return "cuda" if getattr(torch.cuda, "is_available", lambda: False)() else "cpu"
        except Exception:
            return "cpu"

    def _resolve_backend_model_name(self) -> str:
        return PARAKEET_MODEL_NAME_MAP.get(self.model_id, self.model_id)

    def _model_cache_dir(self) -> Path:
        alias = self._resolve_backend_model_name().replace("/", "__")
        return PARAKEET_MODEL_CACHE_DIR / alias

    def _model_dir_has_required_files(self, model_dir: Path, required_files: dict[str, str]) -> bool:
        if not model_dir.exists() or not model_dir.is_dir():
            return False
        for pattern in required_files.values():
            if not list(model_dir.glob(pattern)):
                return False
        return True

    def _load_model(self):
        if self.model is not None:
            return

        if not self.dependency_available():
            raise ParakeetDependencyError(
                "ONNX Parakeet dependencies are not installed. Install onnx-asr[cpu,hub] to use it."
            )

        onnx_asr = importlib.import_module("onnx_asr")
        loader = importlib.import_module("onnx_asr.loader")
        model_name = self._resolve_backend_model_name()
        model_dir = self._model_cache_dir()
        model_dir.parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for quantization in ("int8", None):
            try:
                kwargs: dict[str, Any] = {}
                if quantization:
                    kwargs["quantization"] = quantization
                resolver = loader.create_asr_resolver(model_name)
                required_files = resolver.model_type._get_model_files(quantization)
                if model_dir.exists() and not self._model_dir_has_required_files(model_dir, required_files):
                    shutil.rmtree(model_dir, ignore_errors=True)
                model = onnx_asr.load_model(model_name, str(model_dir), **kwargs)
                try:
                    model = model.with_timestamps()
                    self.timestamps_enabled = True
                except Exception:
                    logger.debug("onnx-asr timestamps are unavailable for model %s", model_name, exc_info=True)
                    self.timestamps_enabled = False
                try:
                    vad = onnx_asr.load_vad("silero")
                    model = model.with_vad(vad)
                    self.vad_enabled = True
                except Exception:
                    logger.debug("onnx-asr VAD is unavailable for model %s", model_name, exc_info=True)
                    self.vad_enabled = False
                self.model = model
                return
            except Exception as exc:
                last_error = exc
                if quantization == "int8":
                    logger.warning("Could not load Parakeet model %s with int8 quantization: %s", model_name, exc)
                    continue
                break

        raise ParakeetDependencyError(f"Failed to load ONNX Parakeet model '{model_name}': {last_error}")

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> dict[str, Any]:
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise Exception(f"Audio file does not exist: {audio_path}")

        self._load_model()
        warnings = []
        if self.runtime == "cpu":
            warnings.append("Parakeet is running on CPU and may be slow.")

        result = await asyncio.to_thread(self.model.recognize, str(audio_file))
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
        language = self._extract_language(result)

        entries = self._flatten_results(result)
        segments: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for entry in entries:
            entry_text = self._extract_text(entry)
            if not entry_text:
                continue
            start_seconds, end_seconds = self._extract_range_seconds(entry)
            if start_seconds is not None and end_seconds is not None:
                segments.append(
                    {
                        "start": format_seconds(start_seconds),
                        "end": format_seconds(end_seconds),
                        "text": entry_text,
                    }
                )
            else:
                text_parts.append(entry_text)

        if not segments and not text_parts:
            fallback_text = self._extract_text(result)
            if fallback_text:
                text_parts.append(fallback_text)

        raw: dict[str, Any] = {"language": language}
        if segments:
            raw["segments"] = segments
        else:
            raw["text"] = "\n\n".join([part for part in text_parts if part]).strip()
            warnings.append("This local model did not return timestamps; transcript was saved without timecodes.")

        return {
            "raw": raw,
            "language": language,
            "timestamps_supported": bool(segments),
            "warnings": warnings,
        }

    def _flatten_results(self, result: Any) -> list[Any]:
        if result is None:
            return []
        if isinstance(result, (str, bytes)):
            return [result]
        if isinstance(result, dict):
            return [result]
        if hasattr(result, "__dict__") and not isinstance(result, (list, tuple, set)):
            return [result]
        if isinstance(result, Iterable):
            flattened = []
            for item in result:
                if isinstance(item, (list, tuple)):
                    flattened.extend(item)
                else:
                    flattened.append(item)
            return flattened
        return [result]

    def _extract_language(self, value: Any) -> str:
        for key in ("language", "lang", "detected_language"):
            if isinstance(value, dict) and value.get(key):
                return str(value.get(key)).strip()
            attr = getattr(value, key, None)
            if attr:
                return str(attr).strip()
        return ""

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("text", "pred_text", "transcript"):
                text = value.get(key)
                if text:
                    return str(text).strip()
            return ""
        for key in ("text", "pred_text", "transcript"):
            text = getattr(value, key, None)
            if text:
                return str(text).strip()
        return ""

    def _extract_range_seconds(self, value: Any) -> tuple[float | None, float | None]:
        direct_start = self._coerce_seconds(self._get_field(value, "start"))
        direct_end = self._coerce_seconds(self._get_field(value, "end"))
        if direct_start is not None and direct_end is not None:
            return direct_start, direct_end

        timestamps = self._get_field(value, "timestamps")
        if timestamps:
            flattened = self._flatten_results(timestamps)
            starts = []
            ends = []
            for item in flattened:
                starts.append(self._coerce_seconds(self._get_field(item, "start")))
                ends.append(self._coerce_seconds(self._get_field(item, "end")))
            valid_starts = [item for item in starts if item is not None]
            valid_ends = [item for item in ends if item is not None]
            if valid_starts and valid_ends:
                return valid_starts[0], valid_ends[-1]

        return None, None

    def _get_field(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _coerce_seconds(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if ":" in text:
                try:
                    parts = [float(part) for part in text.split(":")]
                except ValueError:
                    return None
                seconds = 0.0
                for part in parts:
                    seconds = seconds * 60 + part
                return seconds
            try:
                return float(text)
            except ValueError:
                return None
        return None
