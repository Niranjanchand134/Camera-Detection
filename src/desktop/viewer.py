import cv2
import time
import math
import logging
import ctypes
import numpy as np
from src.config.settings import get_settings
from src.camera.manager import get_camera_manager
from src.detection.detector import get_detector, CATEGORY_LABELS, CATEGORY_COLORS
from src.audio.player import get_audio_player
from src.storage.recorder import VideoRecorder


class DesktopViewer:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.manager = get_camera_manager(self.settings)
        self.detector = get_detector(self.settings)
        self.audio = get_audio_player(self.settings)
        self.recorder = VideoRecorder(fps=self.settings.record_fps, recordings_dir=self.settings.recordings_dir)

        self.window_name = "Crimson Camera Detection System"
        self.view_mode = "grid"
        self.single_camera = None
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.dragging = False
        self.drag_last = (0, 0)
        self.drag_moved = False

        self.navbar_h = 46
        self.right_panel_w = 300
        self.dropdown_open = False
        self.dropdown_rows = {}
        self.is_fullscreen = True
        self.running = True

        self.screen_w, self.screen_h = self._get_screen_size()
        self.content_h = self.screen_h - self.navbar_h
        self.nav_buttons = {"drop": 0, "min": 0, "max": 0, "close": 0}
        self.grid_meta = {"rows": 1, "cols": 1, "tile_w": self.screen_w, "tile_h": self.content_h}
        self.latest_display = None

    def _get_screen_size(self):
        try:
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 1280, 720

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        try:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        except Exception:
            pass
        cv2.setMouseCallback(self.window_name, self._on_mouse)

        print("\n==========================================")
        print("Crimson Desktop Viewer Running")
        print("Controls:")
        print("  Click tile      -> Focus single camera (audio starts)")
        print("  Click / ESC     -> Return to multi-camera grid (audio stops)")
        print("  Scroll / +/-    -> Zoom in/out")
        print("  Drag / WASD     -> Pan while zoomed")
        print("  m               -> Mute/unmute audio")
        print("  r               -> Start/stop recording")
        print("  q               -> Quit")
        print("==========================================\n")

        while self.running:
            cw = self.screen_w - self.right_panel_w if self.detector.get_category() else self.screen_w

            if self.view_mode == "grid":
                names = self.manager.get_camera_names()
                cols = math.ceil(math.sqrt(len(names)))
                rows = math.ceil(len(names) / cols) if cols else 1
                tw = cw // cols if cols else cw
                th = self.content_h // rows if rows else self.content_h
                self.grid_meta.update({"rows": rows, "cols": cols, "tile_w": tw, "tile_h": th})

                tiles = [self.manager.annotate(self.manager.get_raw_frame(n), n, tw, th) for n in names]
                while len(tiles) < rows * cols:
                    tiles.append(np.zeros((th, tw, 3), dtype=np.uint8))
                row_imgs = [np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows)]
                content = np.vstack(row_imgs)
                content = cv2.resize(content, (cw, self.content_h))
            else:
                content = self.manager.build_single(
                    self.single_camera, cw, self.content_h,
                    zoom_level=self.zoom_level, pan_x=self.pan_x, pan_y=self.pan_y
                )

            canvas = np.zeros((self.screen_h, self.screen_w, 3), dtype=np.uint8)
            canvas[self.navbar_h:self.navbar_h + content.shape[0], 0:content.shape[1]] = content

            if self.detector.get_category():
                self._draw_right_panel(canvas, cw)

            self._draw_navbar(canvas)
            if self.dropdown_open:
                self._draw_dropdown(canvas)

            self.latest_display = canvas
            cv2.imshow(self.window_name, canvas)

            raw_key = cv2.waitKeyEx(1)
            key = raw_key & 0xFF if raw_key != -1 else -1

            if key == ord('q'):
                self.running = False
                break
            elif key == 27:  # ESC
                self._back_to_grid()
            elif key == ord('m'):
                self.audio.toggle_mute()
            elif key == ord('r'):
                status = self.recorder.get_status()
                if not status["recording"]:
                    self.recorder.start(lambda: self.latest_display, (self.screen_w, self.screen_h))
                    print("Recording started.")
                else:
                    self.recorder.stop()
                    print("Recording stopped.")

        self.audio.stop()
        self.recorder.stop()
        cv2.destroyAllWindows()

    def _enter_single(self, cam_name: str):
        self.single_camera = cam_name
        self.view_mode = "single"
        self.zoom_level = 1.0
        self.pan_x, self.pan_y = 0, 0
        self.detector.set_scope("single", cam_name)
        self.audio.start(cam_name)

    def _back_to_grid(self):
        self.view_mode = "grid"
        self.single_camera = None
        self.zoom_level = 1.0
        self.pan_x, self.pan_y = 0, 0
        self.detector.set_scope("grid", None)
        self.audio.stop()

    def _draw_navbar(self, canvas):
        cv2.rectangle(canvas, (0, 0), (self.screen_w, self.navbar_h), (25, 27, 33), -1)
        icon_y = self.navbar_h // 2
        spacing = 55
        x_close = self.screen_w - 30
        x_max = x_close - spacing
        x_min = x_max - spacing
        x_drop = x_min - spacing

        pts = np.array([[x_drop - 7, icon_y - 4], [x_drop + 7, icon_y - 4], [x_drop, icon_y + 6]])
        cv2.fillConvexPoly(canvas, pts, (230, 230, 230))
        cv2.line(canvas, (x_min - 8, icon_y), (x_min + 8, icon_y), (230, 230, 230), 2)
        cv2.rectangle(canvas, (x_max - 7, icon_y - 7), (x_max + 7, icon_y + 7), (230, 230, 230), 2)
        cv2.line(canvas, (x_close - 7, icon_y - 7), (x_close + 7, icon_y + 7), (230, 230, 230), 2)
        cv2.line(canvas, (x_close - 7, icon_y + 7), (x_close + 7, icon_y - 7), (230, 230, 230), 2)

        rec_status = self.recorder.get_status()
        if rec_status["recording"]:
            cv2.circle(canvas, (24, icon_y), 7, (0, 0, 255), -1)
            cv2.putText(canvas, f"REC ({rec_status['duration_seconds']}s)", (36, icon_y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        label_x = 130
        cat = self.detector.get_category()
        if cat:
            badge_txt = f"AI: {CATEGORY_LABELS.get(cat, cat.title())}"
            cv2.putText(canvas, badge_txt, (label_x, icon_y + 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, CATEGORY_COLORS.get(cat, (255, 255, 255)), 2)

        self.nav_buttons = {"drop": x_drop, "min": x_min, "max": x_max, "close": x_close}

    def _draw_right_panel(self, canvas, x0):
        cv2.rectangle(canvas, (x0, self.navbar_h), (x0 + self.right_panel_w, self.screen_h), (20, 22, 28), -1)
        cat = self.detector.get_category()
        header = f"{CATEGORY_LABELS.get(cat, '')} Detections"
        if self.view_mode == "single" and self.single_camera:
            header += f" - {self.single_camera}"
        cv2.putText(canvas, header, (x0 + 14, self.navbar_h + 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, (255, 255, 255), 2)

        y = self.navbar_h + 60
        all_dets = self.detector.get_all_detections()
        panel_names = [self.single_camera] if (self.view_mode == "single" and self.single_camera) else self.manager.get_camera_names()

        count = 0
        for cam_name in panel_names:
            for e in all_dets.get(cam_name, []):
                if e["category"] != cat or y > self.screen_h - 20:
                    continue
                cv2.putText(canvas, f"{cam_name}: {e['label'].title()} ({int(e['confidence'] * 100)}%)",
                            (x0 + 14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (220, 220, 220), 1)
                y += 18
                extras = []
                if e.get("speed_kmh"):
                    extras.append(f"Speed: {e['speed_kmh']:.0f} km/h")
                if e.get("plate"):
                    extras.append(f"Plate: {e['plate']}")
                if extras:
                    cv2.putText(canvas, "   " + " | ".join(extras), (x0 + 14, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1)
                    y += 18
                y += 6
                count += 1

        if count == 0:
            cv2.putText(canvas, "Monitoring for detections...", (x0 + 14, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (140, 140, 140), 1)

    def _draw_dropdown(self, canvas):
        panel_w, panel_h = 300, 210
        x0, y0 = self.screen_w - panel_w - 10, self.navbar_h + 5
        cv2.rectangle(canvas, (x0, y0), (x0 + panel_w, y0 + panel_h), (35, 38, 48), -1)

        cv2.putText(canvas, "Select AI Detection Mode:", (x0 + 12, y0 + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1)

        self.dropdown_rows = {}
        active_cat = self.detector.get_category() or "off"
        for i, cat in enumerate(["off", "person", "vehicle"]):
            ry = y0 + 45 + i * 32
            color = CATEGORY_COLORS.get(cat, (200, 200, 200))
            checked = (active_cat == cat)
            cv2.rectangle(canvas, (x0 + 14, ry), (x0 + 30, ry + 16), color, 2)
            if checked:
                cv2.rectangle(canvas, (x0 + 17, ry + 3), (x0 + 27, ry + 13), color, -1)
            cv2.putText(canvas, CATEGORY_LABELS[cat], (x0 + 40, ry + 13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1)
            self.dropdown_rows[cat] = (x0, ry - 6, x0 + panel_w, ry + 26)

    def _on_mouse(self, event, x, y, flags, param):
        if self.dropdown_open and event == cv2.EVENT_LBUTTONDOWN and y > self.navbar_h:
            for cat, (rx1, ry1, rx2, ry2) in self.dropdown_rows.items():
                if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                    self.detector.set_category(cat)
                    self.dropdown_open = False
                    return
            self.dropdown_open = False
            return

        cw = self.screen_w - self.right_panel_w if self.detector.get_category() else self.screen_w

        if event == cv2.EVENT_LBUTTONDOWN and y <= self.navbar_h:
            if abs(x - self.nav_buttons["close"]) < 15:
                self.running = False
            elif abs(x - self.nav_buttons["drop"]) < 15:
                self.dropdown_open = not self.dropdown_open
            return

        if event == cv2.EVENT_LBUTTONDOWN and y > self.navbar_h and x < cw:
            if self.view_mode == "grid":
                names = self.manager.get_camera_names()
                cols, tw, th = self.grid_meta["cols"], self.grid_meta["tile_w"], self.grid_meta["tile_h"]
                col = x // tw
                row = (y - self.navbar_h) // th
                idx = int(row * cols + col)
                if 0 <= idx < len(names):
                    self._enter_single(names[idx])
            else:
                self._back_to_grid()
