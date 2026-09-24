import cv2
import math
import time
import numpy as np
from datetime import datetime
from src.config.settings import get_settings
from src.camera.stream import CameraStream
from src.detection.detector import get_detector, CATEGORY_COLORS


class CameraManager:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.streams = {}
        self.detector = get_detector(self.settings)
        self.detector.set_camera_manager(self)

        for name, url in self.settings.cameras.items():
            self.streams[name] = CameraStream(
                name=name,
                url=url,
                tile_w=self.settings.frame_width,
                tile_h=self.settings.frame_height,
                motion_enabled=self.settings.motion_enabled
            )

    def get_camera_names(self):
        return list(self.streams.keys())

    def get_raw_frame(self, name: str):
        stream = self.streams.get(name)
        return stream.get_frame() if stream else None

    def get_status(self, name: str):
        stream = self.streams.get(name)
        return stream.get_status() if stream else "unknown"

    def get_motion_flag(self, name: str):
        stream = self.streams.get(name)
        return stream.get_motion() if stream else False

    def get_all_statuses(self):
        return {
            name: {
                "status": stream.get_status(),
                "motion": stream.get_motion(),
                "ip": self.settings.camera_ips.get(name, "")
            }
            for name, stream in self.streams.items()
        }

    def annotate(self, frame, name: str, w: int, h: int, crop_offset=(0, 0), crop_size=None):
        if frame is None:
            out = np.zeros((h, w, 3), dtype=np.uint8)
            src_w, src_h = crop_size if crop_size else (w, h)
        else:
            src_h0, src_w0 = frame.shape[:2]
            src_w, src_h = crop_size if crop_size else (src_w0, src_h0)
            out = cv2.resize(frame, (w, h))

        is_online = self.get_status(name) == "online"
        border_color = (40, 200, 60) if is_online else (40, 40, 220)
        border_thickness = max(2, w // 220)
        cv2.rectangle(out, (0, 0), (w - 1, h - 1), border_color, border_thickness)

        font_scale = max(0.45, w / 750)
        
        # Camera name label badge in top-left
        cv2.rectangle(out, (6, 6), (int(140 * font_scale) + 10, int(32 * font_scale)), (20, 20, 25), -1)
        cv2.putText(out, name, (12, int(24 * font_scale)), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        # Timestamp in bottom-left
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(out, timestamp, (12, h - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale * 0.75, (230, 230, 230), 1, cv2.LINE_AA)

        # Offline status indicator
        if not is_online:
            cv2.putText(out, "OFFLINE", (w // 2 - int(70 * font_scale), h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale * 1.1, (50, 50, 240), 2, cv2.LINE_AA)

        # Motion flag indicator in top-right
        if self.settings.motion_enabled and self.get_motion_flag(name):
            cv2.rectangle(out, (w - int(95 * font_scale), 6), (w - 6, int(30 * font_scale)), (0, 140, 255), -1)
            cv2.putText(out, "MOTION", (w - int(90 * font_scale), int(22 * font_scale)),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.65, (255, 255, 255), 1, cv2.LINE_AA)

        # AI Detection boxes overlay
        active_cat = self.detector.get_category()
        if active_cat and src_w > 0 and src_h > 0:
            ox, oy = crop_offset
            scale_x = w / src_w
            scale_y = h / src_h
            entries = self.detector.get_detections(name)

            for e in entries:
                x1, y1, x2, y2 = e["px_box"]
                rx1, ry1, rx2, ry2 = x1 - ox, y1 - oy, x2 - ox, y2 - oy
                rx1c = max(0.0, min(float(src_w), rx1))
                ry1c = max(0.0, min(float(src_h), ry1))
                rx2c = max(0.0, min(float(src_w), rx2))
                ry2c = max(0.0, min(float(src_h), ry2))

                if rx2c <= rx1c or ry2c <= ry1c:
                    continue

                bx1, by1 = int(rx1c * scale_x), int(ry1c * scale_y)
                bx2, by2 = int(rx2c * scale_x), int(ry2c * scale_y)
                color = CATEGORY_COLORS.get(e["category"], (255, 255, 255))
                
                # Bounding box
                cv2.rectangle(out, (bx1, by1), (bx2, by2), color, max(1, w // 320))

                label_txt = f"{e['label'].title()} {int(e['confidence'] * 100)}%"
                if e.get("speed_kmh"):
                    label_txt += f" | {e['speed_kmh']:.0f}km/h"

                # Label tag background
                (tw, th_box), _ = cv2.getTextSize(label_txt, cv2.FONT_HERSHEY_SIMPLEX, max(0.35, font_scale * 0.55), 1)
                label_y1 = max(th_box + 6, by1)
                cv2.rectangle(out, (bx1, label_y1 - th_box - 4), (bx1 + tw + 6, label_y1 + 2), (20, 20, 20), -1)
                cv2.putText(out, label_txt, (bx1 + 3, label_y1 - 2), cv2.FONT_HERSHEY_SIMPLEX,
                            max(0.35, font_scale * 0.55), color, 1, cv2.LINE_AA)

                if e.get("plate"):
                    plate_txt = f"Plate: {e['plate']}"
                    (ptw, pth), _ = cv2.getTextSize(plate_txt, cv2.FONT_HERSHEY_SIMPLEX, max(0.35, font_scale * 0.5), 1)
                    py = min(h - 8, by2 + pth + 6)
                    cv2.rectangle(out, (bx1, py - pth - 4), (bx1 + ptw + 6, py + 2), (20, 20, 20), -1)
                    cv2.putText(out, plate_txt, (bx1 + 3, py - 2),
                                cv2.FONT_HERSHEY_SIMPLEX, max(0.35, font_scale * 0.5), (0, 240, 255), 1, cv2.LINE_AA)

        return out

    def build_grid(self, w: int = 1280, h: int = 720):
        names = self.get_camera_names()
        n = len(names)
        if n == 0:
            return np.zeros((h, w, 3), dtype=np.uint8)

        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        tile_w = w // cols
        tile_h = h // rows

        tiles = []
        for name in names:
            raw = self.get_raw_frame(name)
            annotated = self.annotate(raw, name, tile_w, tile_h)
            tiles.append(annotated)

        while len(tiles) < rows * cols:
            tiles.append(np.zeros((tile_h, tile_w, 3), dtype=np.uint8))

        row_images = [np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows)]
        grid = np.vstack(row_images)
        return cv2.resize(grid, (w, h))

    def build_single(self, cam_name: str, w: int = 1280, h: int = 720, zoom_level: float = 1.0, pan_x: int = 0, pan_y: int = 0):
        raw = self.get_raw_frame(cam_name)
        if raw is None:
            return self.annotate(None, cam_name, w, h)

        fh, fw = raw.shape[:2]
        crop_w = max(1, int(fw / max(1.0, zoom_level)))
        crop_h = max(1, int(fh / max(1.0, zoom_level)))

        max_pan_x = max(0, (fw - crop_w) // 2)
        max_pan_y = max(0, (fh - crop_h) // 2)
        px = max(-max_pan_x, min(max_pan_x, pan_x))
        py = max(-max_pan_y, min(max_pan_y, pan_y))

        cx = fw // 2 + px
        cy = fh // 2 + py
        x0 = max(0, min(fw - crop_w, cx - crop_w // 2))
        y0 = max(0, min(fh - crop_h, cy - crop_h // 2))
        cropped = raw[y0:y0 + crop_h, x0:x0 + crop_w]

        return self.annotate(cropped, cam_name, w, h, crop_offset=(x0, y0), crop_size=(crop_w, crop_h))

    def generate_mjpeg_stream(self, target: str = "grid", fps: int = 15, w: int = 960, h: int = 540):
        interval = 1.0 / max(1, fps)
        while True:
            t0 = time.time()
            if target == "grid":
                frame = self.build_grid(w=w, h=h)
            else:
                frame = self.build_single(target, w=w, h=h)

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

            elapsed = time.time() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


_camera_manager_instance = None


def get_camera_manager(settings=None) -> CameraManager:
    global _camera_manager_instance
    if _camera_manager_instance is None:
        _camera_manager_instance = CameraManager(settings)
    return _camera_manager_instance
