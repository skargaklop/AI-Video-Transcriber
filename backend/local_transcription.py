import importlib
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from parakeet_transcriber import PARAKEET_MODEL_PRESETS, ParakeetLocalTranscriber
from transcriber import WHISPER_MODEL_PRESETS, WhisperLocalTranscriber
from video_processor import ensure_ffmpeg_binary


logger = logging.getLogger(__name__)

DEFAULT_LOCAL_BACKEND = "whisper"
DEFAULT_WHISPER_MODEL = "base"
DEFAULT_PARAKEET_MODEL = PARAKEET_MODEL_PRESETS[0]
LOCAL_BACKEND_PACKAGES = {
    "whisper": ["faster-whisper>=1.1.0"],
    "parakeet": ["nemo_toolkit[asr]>=2.0.0"],
}


class LocalTranscriptionError(Exception):
    """Raised when local transcription cannot run."""


def _python_version_tuple() -> tuple[int, int]:
    version_info = getattr(sys, "version_info", (0, 0))
    try:
        major = int(version_info[0])
        minor = int(version_info[1])
    except Exception:
        major, minor = 0, 0
    return major, minor


def _backend_install_constraints(backend: str) -> dict[str, Any]:
    normalized_backend = (backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    if normalized_backend != "parakeet":
        return {"auto_install_supported": True, "warning_code": "", "message": ""}

    major, minor = _python_version_tuple()
    if sys.platform.startswith("win") and (major, minor) >= (3, 13):
        return {
            "auto_install_supported": False,
            "warning_code": "parakeet_windows_py313_requires_build_tools",
            "message": (
                "Automatic Parakeet dependency installation is not supported on Windows with Python 3.13 in this app runtime. "
                "The NeMo ASR dependency chain pulls editdistance, which has no prebuilt CPython 3.13 Windows wheel, "
                "so pip falls back to a source build that requires Microsoft C++ Build Tools. "
                "Use the Whisper backend, install Microsoft C++ Build Tools and the Parakeet dependencies manually, "
                "or run Parakeet from a Python 3.12 environment."
            ),
        }

    return {"auto_install_supported": True, "warning_code": "", "message": ""}


def install_backend_dependencies(backend: str) -> None:
    normalized_backend = (backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    packages = LOCAL_BACKEND_PACKAGES.get(normalized_backend)
    if not packages:
        raise LocalTranscriptionError(f"Unsupported local backend: {backend}")

    constraints = _backend_install_constraints(normalized_backend)
    if not constraints["auto_install_supported"]:
        raise LocalTranscriptionError(constraints["message"])

    logger.info("Installing missing dependencies for local backend: %s", normalized_backend)
    for package in packages:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise LocalTranscriptionError(
                f"Failed to install dependencies for local backend '{normalized_backend}': {exc.stderr or exc}"
            ) from exc
    importlib.invalidate_caches()


def ensure_backend_dependencies(backend: str, importlib_module: Any = importlib) -> None:
    normalized_backend = (backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    checker = _dependency_checker(normalized_backend)
    if checker is None:
        raise LocalTranscriptionError(f"Unsupported local backend: {backend}")
    if checker(importlib_module):
        return
    install_backend_dependencies(normalized_backend)
    if not checker(importlib_module):
        raise LocalTranscriptionError(
            f"Dependencies for local backend '{normalized_backend}' were installed but the backend is still unavailable."
        )


def detect_runtime(importlib_module: Any = importlib) -> str:
    try:
        if importlib_module.util.find_spec("torch") is None:
            return "cpu"
        torch = importlib_module.import_module("torch")
        return "cuda" if getattr(torch.cuda, "is_available", lambda: False)() else "cpu"
    except Exception:
        return "cpu"


def _dependency_checker(backend: str):
    availability_checks = {
        "whisper": WhisperLocalTranscriber.dependency_available,
        "parakeet": ParakeetLocalTranscriber.dependency_available,
    }
    return availability_checks.get((backend or DEFAULT_LOCAL_BACKEND).strip().lower())


def backend_dependencies_available(backend: str, importlib_module: Any = importlib) -> bool:
    checker = _dependency_checker(backend)
    if checker is None:
        raise LocalTranscriptionError(f"Unsupported local backend: {backend}")
    return checker(importlib_module)


def get_local_capabilities(importlib_module: Any = importlib) -> dict[str, Any]:
    runtime = detect_runtime(importlib_module)
    whisper_available = WhisperLocalTranscriber.dependency_available(importlib_module)
    parakeet_available = ParakeetLocalTranscriber.dependency_available(importlib_module)
    parakeet_constraints = _backend_install_constraints("parakeet")

    return {
        "runtime": runtime,
        "backends": {
            "whisper": {
                "available": whisper_available,
                "runtime": runtime,
                "warning_code": "",
                "warning": "",
                "presets": WHISPER_MODEL_PRESETS,
                "default_preset": DEFAULT_WHISPER_MODEL,
                "custom_supported": True,
                "auto_install": True,
            },
            "parakeet": {
                "available": parakeet_available,
                "runtime": runtime,
                "warning_code": (
                    "parakeet_cpu_slow"
                    if parakeet_available and runtime == "cpu"
                    else parakeet_constraints["warning_code"]
                ),
                "warning": "" if parakeet_available else parakeet_constraints["message"],
                "presets": PARAKEET_MODEL_PRESETS,
                "default_preset": DEFAULT_PARAKEET_MODEL,
                "custom_supported": True,
                "auto_install": parakeet_constraints["auto_install_supported"],
            },
        },
    }


def resolve_local_model_id(local_backend: str, local_model_preset: str = "", local_model_id: str = "") -> str:
    backend = (local_backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    preset = (local_model_preset or "").strip()
    custom = (local_model_id or "").strip()

    if preset == "custom" and custom:
        return custom
    if custom and not preset:
        return custom
    if preset and preset != "custom":
        return preset
    if backend == "parakeet":
        return DEFAULT_PARAKEET_MODEL
    return DEFAULT_WHISPER_MODEL


def build_local_transcriber(
    local_backend: str,
    local_model_preset: str = "",
    local_model_id: str = "",
) -> Any:
    backend = (local_backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    ensure_backend_dependencies(backend)
    resolved_model_id = resolve_local_model_id(backend, local_model_preset, local_model_id)

    if backend == "parakeet":
        return ParakeetLocalTranscriber(resolved_model_id)
    if backend == "whisper":
        return WhisperLocalTranscriber(resolved_model_id)
    raise LocalTranscriptionError(f"Unsupported local backend: {local_backend}")


def prepare_local_transcriber(
    local_backend: str,
    local_model_preset: str = "",
    local_model_id: str = "",
) -> tuple[Any, str]:
    backend = (local_backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    resolved_model_id = resolve_local_model_id(backend, local_model_preset, local_model_id)
    transcriber = build_local_transcriber(backend, local_model_preset, local_model_id)
    preload = getattr(transcriber, "_load_model", None)
    if callable(preload):
        preload()
    return transcriber, resolved_model_id


def preload_local_transcriber(transcriber: Any) -> None:
    preload = getattr(transcriber, "_load_model", None)
    if callable(preload):
        preload()


def ensure_backend_audio_file(audio_path: str, backend: str, output_dir: Path) -> str:
    normalized_backend = (backend or DEFAULT_LOCAL_BACKEND).strip().lower()
    if normalized_backend != "parakeet":
        return audio_path

    source = Path(audio_path)
    if source.suffix.lower() == ".wav":
        return str(source)

    output_dir.mkdir(exist_ok=True)
    target = output_dir / f"{source.stem}_parakeet.wav"
    cmd = [
        ensure_ffmpeg_binary(),
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(target),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise LocalTranscriptionError(f"Failed to convert audio for Parakeet: {exc.stderr or exc}") from exc

    return str(target)
