import cv2
import time
import logging
import threading
import numpy as np


class CameraStream:
    def __init__(self, name: str, url: str, tile_w: int = 480, tile_h: int = 270, motion_enabled: bool = True):
        self.name = name
        self.url = url
        self.tile_w = tile_w
        self.tile_h = tile_h
        self.motion_enabled = motion_enabled

        self.latest_frame = None
        self.status = "connecting"  # "online" | "offline" | "connecting"
        self.motion_flag = False
        self.last_frame_time = 0.0

        self.running = True
        self.lock = threading.Lock()

        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def get_frame(self):
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_status(self):
        with self.lock:
            return self.status

    def get_motion(self):
        with self.lock:
            return self.motion_flag

    def _capture_loop(self):
        prev_gray = None

        while self.running:
            logging.info(f"{self.name}: Connecting to stream...")
            with self.lock:
                self.status = "connecting"

            cap = cv2.VideoCapture(self.url)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                with self.lock:
                    self.status = "offline"
                logging.warning(f"{self.name}: Could not open stream, retrying in 5s")
                time.sleep(5)
                continue

            with self.lock:
                self.status = "online"
            logging.info(f"{self.name}: Connected successfully.")

            while self.running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    with self.lock:
                        self.status = "offline"
                    logging.warning(f"{self.name}: Lost connection, reconnecting...")
                    break

                # Motion detection calculation
                has_motion = False
                if self.motion_enabled:
                    try:
                        small = cv2.resize(frame, (self.tile_w, self.tile_h))
                        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        gray = cv2.GaussianBlur(gray, (21, 21), 0)
                        if prev_gray is not None:
                            diff = cv2.absdiff(prev_gray, gray)
                            thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                            has_motion = bool(np.sum(thresh) > (self.tile_w * self.tile_h * 2))
                        prev_gray = gray
                    except Exception as e:
                        logging.debug(f"{self.name} motion error: {e}")

                with self.lock:
                    self.latest_frame = frame
                    self.status = "online"
                    self.motion_flag = has_motion
                    self.last_frame_time = time.time()

            cap.release()
            with self.lock:
                self.status = "offline"
            time.sleep(3)

    def stop(self):
        self.running = False
