#!/usr/bin/env python3
"""
AI视频转录器启动脚本
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
import urllib.request
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
            break  # server responded
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)

def check_dependencies():
    """检查依赖是否安装"""
    required_packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "yt-dlp": "yt_dlp",
        "openai": "openai"
    }

    missing_packages = []
    for display_name, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(display_name)

    if missing_packages:
        print("❌ 缺少以下依赖包:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n请运行以下命令安装依赖:")
        print("pip install -r requirements.txt")
        return False

    print("✅ 所有依赖已安装")
    return True


def report_optional_local_backends():
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
        print("ℹ️  Optional local backends available:")
        for package in available:
            print(f"   - {package}")
    if missing:
        print("ℹ️  Optional local backends not installed:")
        for package in missing:
            print(f"   - {package}")
        print("   The app will still start. These backends remain unavailable until installed.")

def setup_environment():
    """设置环境变量"""
    # 设置OpenAI配置
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  未设置OPENAI_API_KEY。可以在浏览器设置中填写摘要API Key。")
        return False
    
    print("✅ 已设置OpenAI API Key")
    
    if not os.getenv("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = "https://oneapi.basevec.com/v1"
        print("✅ 已设置OpenAI Base URL")
    
    print("🔑 OpenAI API已配置，摘要功能可用")
    return True

def main():
    """主函数"""
    # 检查是否使用生产模式（禁用热重载）
    production_mode = "--prod" in sys.argv or os.getenv("PRODUCTION_MODE") == "true"
    
    print("🚀 AI视频转录器启动检查")
    if production_mode:
        print("🔒 生产模式 - 热重载已禁用")
    else:
        print("🔧 开发模式 - 热重载已启用")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    report_optional_local_backends()
    
    # 设置环境
    setup_environment()
    
    print("\n🎉 启动检查完成!")
    print("=" * 50)
    
    # 启动服务器
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8001))
    
    print(f"\n🌐 启动服务器...")
    print(f"   地址: http://localhost:{port}")
    print(f"   按 Ctrl+C 停止服务")
    print("=" * 50)
    
    try:
        # 切换到backend目录并启动服务
        backend_dir = Path(__file__).parent / "backend"
        os.chdir(backend_dir)
        
        cmd = [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", host,
            "--port", str(port)
        ]
        
        # 只在开发模式下启用热重载
        if not production_mode:
            cmd.append("--reload")
        
        # Open browser automatically once the server is ready
        url = f"http://localhost:{port}"
        t = threading.Thread(target=open_browser, args=(url,), daemon=True)
        t.start()

        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
