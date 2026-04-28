#!/usr/bin/env python3
"""Startup script for AI Video Transcriber."""

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def open_browser(url: str, timeout: int = 15) -> None:
    """Wait until the server is up, then open the browser."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)


def check_dependencies() -> bool:
    """Check whether required Python packages are installed."""
    required_packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "yt-dlp": "yt_dlp",
        "openai": "openai",
    }

    missing_packages = []
    for display_name, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(display_name)

    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\nInstall them with:")
        print("pip install -r requirements.txt")
        return False

    print("All required packages are installed.")
    return True


def report_optional_local_backends() -> None:
    """Report optional local transcription backend availability."""
    optional_packages = {
        "faster-whisper (Whisper local backend)": "faster_whisper",
        "NVIDIA NeMo (Parakeet local backend)": "nemo",
    }
    available = []
    missing = []

    for display_name, import_name in optional_packages.items():
        try:
            __import__(import_name)
            available.append(display_name)
        except ImportError:
            missing.append(display_name)

    if available:
        print("Optional local backends available:")
        for package in available:
            print(f"   - {package}")
    if missing:
        print("Optional local backends not installed:")
        for package in missing:
            print(f"   - {package}")
        print("   The app will still start. These backends remain unavailable until installed.")


def setup_environment() -> bool:
    """Set optional server-side environment defaults."""
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. You can still enter a summary API key in the browser UI.")
        return False

    print("OpenAI API key is set.")

    if not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = "https://oneapi.basevec.com/v1"
        print("OpenAI Base URL was not set. Applied default server-side base URL.")

    print("OpenAI summary provider is configured for server-side defaults.")
    return True


def main() -> None:
    """Start the API server."""
    production_mode = "--prod" in sys.argv or os.getenv("PRODUCTION_MODE") == "true"

    print("AI Video Transcriber startup check")
    if production_mode:
        print("Production mode - hot reload disabled")
    else:
        print("Development mode - hot reload enabled")
    print("=" * 50)

    if not check_dependencies():
        sys.exit(1)
    report_optional_local_backends()
    setup_environment()

    print("\nStartup checks complete.")
    print("=" * 50)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8001))

    print("\nStarting server...")
    print(f"   URL: http://localhost:{port}")
    print("   Press Ctrl+C to stop the server")
    print("=" * 50)

    try:
        backend_dir = Path(__file__).parent / "backend"
        os.chdir(backend_dir)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            host,
            "--port",
            str(port),
        ]

        if not production_mode:
            cmd.append("--reload")

        url = f"http://localhost:{port}"
        t = threading.Thread(target=open_browser, args=(url,), daemon=True)
        t.start()

        subprocess.run(cmd)

    except KeyboardInterrupt:
        print("\n\nServer stopped.")
    except Exception as exc:
        print(f"\nStartup failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
