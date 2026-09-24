import os
import json
import logging
from urllib.parse import quote
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# Force RTSP over TCP for resilient streaming
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")


class Settings:
    def __init__(self):
        # Read config.json
        config_path = BASE_DIR / "config.json"
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                logging.error(f"Error reading config.json: {e}")

        # Credentials & network settings from .env (with fallbacks to config.json or defaults)
        self.username = os.getenv("CAMERA_USERNAME") or config.get("username", "admin")
        raw_password = os.getenv("CAMERA_PASSWORD") or config.get("password", "")
        self.raw_password = raw_password
        self.encoded_password = quote(raw_password, safe="")
        self.port = int(os.getenv("CAMERA_PORT") or config.get("port", 554))
        self.default_channel = str(os.getenv("CAMERA_DEFAULT_CHANNEL") or config.get("channel", "101"))

        # Cameras map: parse CAMERA_1_NAME/CAMERA_1_IP or CAMERA_X... or fallback to config["cameras"]
        self.cameras = {}
        self.camera_ips = {}

        # 1. First check environment variables
        for i in range(1, 33):
            cam_name = os.getenv(f"CAMERA_{i}_NAME")
            cam_ip = os.getenv(f"CAMERA_{i}_IP")
            if cam_name and cam_ip:
                self.cameras[cam_name.strip()] = self.build_rtsp_url(cam_ip.strip(), self.default_channel)
                self.camera_ips[cam_name.strip()] = cam_ip.strip()

        # 2. If no cameras configured in .env, fallback to config.json
        if not self.cameras and "cameras" in config:
            for cam_name, cam_ip in config["cameras"].items():
                self.cameras[cam_name] = self.build_rtsp_url(cam_ip, self.default_channel)
                self.camera_ips[cam_name] = cam_ip

        # App & Media settings
        self.frame_width = int(config.get("frame_width", 480))
        self.frame_height = int(config.get("frame_height", 270))
        self.motion_enabled = bool(config.get("motion_detection", True))
        self.record_fps = int(config.get("record_fps", 10))

        # Folders
        self.recordings_dir = str(BASE_DIR / config.get("recordings_folder", "recordings"))
        self.snapshots_dir = str(BASE_DIR / config.get("snapshots_folder", "snapshots"))
        self.log_file = str(BASE_DIR / "camera_system.log")
        self.db_file = str(BASE_DIR / "camera_records.db")

        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)

        # AI Detection settings
        det_cfg = config.get("detection", {})
        self.yolo_model = det_cfg.get("yolo_model", "yolo26m.pt")
        self.confidence_threshold = float(det_cfg.get("confidence_threshold", 0.5))
        self.detect_interval_sec = max(0.05, float(det_cfg.get("detect_interval_sec", 0.5)))
        self.inference_size = int(det_cfg.get("inference_size", 320))
        self.pixels_per_meter = max(1e-3, float(det_cfg.get("pixels_per_meter", 20.0)))
        self.plate_ocr_enabled = bool(det_cfg.get("plate_ocr_enabled", True))

        # Audio settings
        audio_cfg = config.get("audio", {})
        self.audio_enabled = bool(audio_cfg.get("enabled", True))
        self.audio_samplerate = int(audio_cfg.get("samplerate", 44100))

        # Web Server settings
        web_cfg = config.get("web", {})
        self.web_host = os.getenv("WEB_HOST") or web_cfg.get("host", "0.0.0.0")
        self.web_port = int(os.getenv("WEB_PORT") or web_cfg.get("port", 5000))
        self.secret_key = os.getenv("SECRET_KEY") or "crimson-camera-secure-key"

    def build_rtsp_url(self, ip: str, channel: str = None) -> str:
        ch = channel or self.default_channel
        return f"rtsp://{self.username}:{self.encoded_password}@{ip}:{self.port}/Streaming/Channels/{ch}"

    def audio_candidate_urls(self, cam_name: str) -> list:
        if cam_name not in self.camera_ips:
            return []
        ip = self.camera_ips[cam_name]
        tried = [self.default_channel]
        if self.default_channel.endswith("01"):
            tried.append(self.default_channel[:-2] + "02")
        elif self.default_channel.endswith("02"):
            tried.append(self.default_channel[:-2] + "01")
        return [self.build_rtsp_url(ip, ch) for ch in tried]


_settings_instance = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
