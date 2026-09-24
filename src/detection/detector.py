import time
import logging
import threading
import numpy as np
from src.config.settings import get_settings
from src.detection.tracker import CentroidSpeedTracker
from src.detection.plate_ocr import detect_plate_text
from src.storage.database import get_db

CATEGORY_MAP = {
    "person": {"person"},
    "vehicle": {"car", "truck", "motorcycle", "bus"},
}

CATEGORY_LABELS = {
    "off": "Off",
    "person": "Person",
    "vehicle": "Vehicle",
}

CATEGORY_COLORS = {  # BGR for OpenCV
    "off": (150, 150, 150),
    "person": (255, 80, 0),      # Blue-Orange accent
    "vehicle": (0, 220, 255),    # Amber/Yellow accent
}

SPEED_CATEGORIES = {"vehicle"}


class AIDetector:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.active_category = None  # None ("off"), "person", "vehicle"
        self.lock = threading.Lock()
        self.running = True

        self.detections = {name: [] for name in self.settings.cameras.keys()}
        self.tracker = CentroidSpeedTracker(pixels_per_meter=self.settings.pixels_per_meter)
        self.db = get_db()

        self.camera_manager = None
        self.view_scope = ("grid", None)  # (mode, single_camera)
        self.last_db_log = {}  # (camera, category, label) -> last log timestamp

        # Load YOLO model
        self.model = None
        self.name_to_id = {}
        self._load_model()

        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            logging.info(f"Loading YOLO model '{self.settings.yolo_model}'...")
            self.model = YOLO(self.settings.yolo_model)
            self.name_to_id = {cls_name.lower(): idx for idx, cls_name in self.model.names.items()}
            logging.info("YOLO model successfully loaded.")
        except Exception as e:
            self.model = None
            logging.error(f"Failed to load YOLO model: {e}")

    def set_camera_manager(self, manager):
        self.camera_manager = manager

    def set_category(self, cat: str):
        with self.lock:
            if not cat or cat.lower() == "off":
                self.active_category = None
            else:
                self.active_category = cat.lower()

            if self.active_category is None:
                for cam in self.detections:
                    self.detections[cam] = []
        logging.info(f"AI detection category changed to: {self.active_category}")

    def get_category(self):
        with self.lock:
            return self.active_category

    def set_scope(self, mode: str, single_camera: str = None):
        with self.lock:
            self.view_scope = (mode, single_camera)

    def get_detections(self, camera_name: str) -> list:
        with self.lock:
            return list(self.detections.get(camera_name, []))

    def get_all_detections(self) -> dict:
        with self.lock:
            return {cam: list(dets) for cam, dets in self.detections.items()}

    def _worker_loop(self):
        last_run = {}
        last_scope = None

        while self.running:
            if self.model is None or self.active_category is None or self.camera_manager is None:
                time.sleep(0.2)
                continue

            with self.lock:
                scope_mode, scope_camera = self.view_scope
                active_cat = self.active_category

            # Clear stale camera detections when switching scope
            current_scope = (scope_mode, scope_camera)
            if current_scope != last_scope:
                with self.lock:
                    all_cams = list(self.detections.keys())
                    target_names = {scope_camera} if (scope_mode == "single" and scope_camera) else set(all_cams)
                    for n in all_cams:
                        if n not in target_names:
                            self.detections[n] = []
                last_scope = current_scope

            camera_names = [scope_camera] if (scope_mode == "single" and scope_camera) else list(self.settings.cameras.keys())

            did_work = False
            for cam_name in camera_names:
                if not self.running or self.active_category is None:
                    break

                now = time.time()
                if now - last_run.get(cam_name, 0.0) < self.settings.detect_interval_sec:
                    continue

                frame = self.camera_manager.get_raw_frame(cam_name)
                if frame is None:
                    continue

                try:
                    self._run_detection_pass(cam_name, frame.copy(), active_cat, now)
                except Exception as e:
                    logging.error(f"{cam_name}: Detection pass error: {e}")

                last_run[cam_name] = time.time()
                did_work = True

            if not did_work:
                time.sleep(0.03)

    def _run_detection_pass(self, cam_name: str, frame: np.ndarray, active_cat: str, now: float):
        wanted_ids = [self.name_to_id[n] for n in CATEGORY_MAP.get(active_cat, set()) if n in self.name_to_id]
        if not wanted_ids:
            with self.lock:
                self.detections[cam_name] = []
            return

        fh, fw = frame.shape[:2]
        results = self.model(
            frame,
            conf=self.settings.confidence_threshold,
            classes=wanted_ids,
            imgsz=self.settings.inference_size,
            verbose=False
        )

        entries = []
        if results and len(results) > 0:
            for box in results[0].boxes:
                confidence = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = self.model.names.get(cls_id, "object")

                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(float(fw), x2), min(float(fh), y2)
                px_box = (int(x1), int(y1), int(x2), int(y2))

                entries.append({
                    "label": cls_name,
                    "category": active_cat,
                    "confidence": confidence,
                    "px_box": px_box,
                    "speed_kmh": None,
                    "plate": None,
                })

        if active_cat in SPEED_CATEGORIES and entries:
            speeds = self.tracker.update(cam_name, active_cat, [e["px_box"] for e in entries], now)
            for e, s in zip(entries, speeds):
                e["speed_kmh"] = s
                try:
                    x1, y1, x2, y2 = e["px_box"]
                    crop = frame[max(0, y1):max(1, y2), max(0, x1):max(1, x2)]
                    e["plate"] = detect_plate_text(crop, self.settings.plate_ocr_enabled)
                except Exception:
                    e["plate"] = None

        with self.lock:
            self.detections[cam_name] = entries

        # Log event to database with throttling (cooldown 4 seconds per category/label)
        motion_status = self.camera_manager.get_motion_flag(cam_name) if self.camera_manager else False
        for e in entries:
            log_key = (cam_name, e["category"], e["label"])
            last_time = self.last_db_log.get(log_key, 0.0)
            if now - last_time >= 4.0:
                self.last_db_log[log_key] = now
                x1, y1, x2, y2 = e["px_box"]
                crop = frame[max(0, y1):max(1, y2), max(0, x1):max(1, x2)]
                self.db.insert_event(
                    camera_name=cam_name,
                    category=e["category"],
                    label=e["label"],
                    confidence=e["confidence"],
                    speed_kmh=e["speed_kmh"],
                    plate_text=e["plate"],
                    frame_crop=crop,
                    motion_flag=motion_status
                )

    def stop(self):
        self.running = False


_detector_instance = None


def get_detector(settings=None) -> AIDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AIDetector(settings)
    return _detector_instance
