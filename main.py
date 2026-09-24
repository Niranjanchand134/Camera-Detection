#!/usr/bin/env python3
"""
Crimson Vision - Camera Intelligence & Detection System
Unified Application Launcher
"""

import sys
import argparse
import logging
from src.config.settings import get_settings
from src.storage.database import get_db
from src.storage.recorder import get_recorder
from src.detection.detector import get_detector
from src.audio.player import get_audio_player
from src.camera.manager import get_camera_manager
from src.web.app import create_app


def setup_logging(settings):
    logging.basicConfig(
        filename=settings.log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)


def run_web(settings, host=None, port=None):
    h = host or settings.web_host
    p = port or settings.web_port

    print("\n==========================================================")
    print("  CRIMSON VISION - CAMERA INTELLIGENCE SYSTEM")
    print("==========================================================")
    print(f"  * Web Server:        http://{h if h != '0.0.0.0' else 'localhost'}:{p}")
    print(f"  * Live Monitoring:   http://{h if h != '0.0.0.0' else 'localhost'}:{p}/live")
    print(f"  * Records & Reports:  http://{h if h != '0.0.0.0' else 'localhost'}:{p}/records")
    print(f"  * Configured Cams:   {len(settings.cameras)}")
    print(f"  * AI Model:          {settings.yolo_model}")
    print(f"  * Recordings Dir:    {settings.recordings_dir}")
    print("==========================================================\n")

    manager = get_camera_manager(settings)
    detector = get_detector(settings)
    audio = get_audio_player(settings)
    recorder = get_recorder(settings=settings, fps=settings.record_fps)
    db = get_db()

    app = create_app(
        manager=manager,
        detector=detector,
        audio_player=audio,
        recorder=recorder,
        db=db
    )

    try:
        app.run(host=h, port=p, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    finally:
        recorder.stop()
        detector.stop()


def run_desktop(settings):
    from src.desktop.viewer import DesktopViewer
    viewer = DesktopViewer(settings)
    viewer.run()


def main():
    parser = argparse.ArgumentParser(description="Crimson Vision Camera Detection System")
    parser.add_argument("--mode", choices=["web", "desktop"], default="web",
                        help="Run mode: 'web' for modern Web Dashboard (default), 'desktop' for OpenCV GUI window")
    parser.add_argument("--host", type=str, default=None, help="Host IP for web server (default from .env or 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Port for web server (default from .env or 5000)")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings)

    if args.mode == "desktop":
        run_desktop(settings)
    else:
        run_web(settings, host=args.host, port=args.port)


if __name__ == "__main__":
    main()