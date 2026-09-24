import os
import cv2
import time
import logging
import threading
import numpy as np
from datetime import datetime
from src.config.settings import get_settings

try:
    import av
    AV_AVAILABLE = True
except Exception:
    av = None
    AV_AVAILABLE = False


class SingleCameraRecorder:
    """
    Records a camera's video stream with synchronized audio into an MP4 file.
    """
    def __init__(self, camera_name: str, frame_provider, frame_size=(1280, 720),
                 fps: int = 15, audio_urls: list = None, recordings_dir: str = "recordings"):
        self.camera_name = camera_name
        self.frame_provider = frame_provider
        self.frame_size = frame_size
        self.fps = fps
        self.audio_urls = audio_urls or []
        self.recordings_dir = recordings_dir

        self.recording = False
        self.start_time = None
        self.video_thread = None
        self.audio_thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        # Output file paths
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%Y%m%d_%H%M%S")
        safe_cam = "".join(c if c.isalnum() else "_" for c in self.camera_name).strip("_")

        cam_dir = os.path.join(self.recordings_dir, date_str, self.camera_name)
        os.makedirs(cam_dir, exist_ok=True)

        self.filename = f"recording_{safe_cam}_{time_str}.mp4"
        self.rel_path = f"{date_str}/{self.camera_name}/{self.filename}"
        self.full_path = os.path.join(cam_dir, self.filename)

        # PyAV / OpenCV writer handles
        self.writer_type = None
        self.av_container = None
        self.v_stream = None
        self.a_stream = None
        self.a_resampler = None
        self.cv_writer = None

    def start(self):
        with self.lock:
            if self.recording:
                return
            self.stop_event.clear()
            w, h = self.frame_size

            # 1. Setup PyAV Container with H.264 Video and AAC Audio
            if AV_AVAILABLE:
                try:
                    self.av_container = av.open(self.full_path, mode="w")
                    
                    # Video stream
                    self.v_stream = self.av_container.add_stream("h264", rate=self.fps)
                    self.v_stream.width = w
                    self.v_stream.height = h
                    self.v_stream.pix_fmt = "yuv420p"
                    self.v_stream.options = {"crf": "23", "preset": "veryfast"}

                    # Optional Audio stream (if audio URL configured)
                    if self.audio_urls:
                        try:
                            self.a_stream = self.av_container.add_stream("aac", rate=16000)
                            self.a_stream.bit_rate = 32000
                            self.a_resampler = av.audio.resampler.AudioResampler(
                                format="fltp", layout="mono", rate=16000
                            )
                        except Exception as e:
                            logging.debug(f"{self.camera_name}: Audio stream setup skipped: {e}")
                            self.a_stream = None

                    self.writer_type = "av"
                    logging.info(f"PyAV A/V recorder initialized for '{self.camera_name}' -> {self.full_path}")
                except Exception as e:
                    logging.warning(f"{self.camera_name}: PyAV writer init failed: {e}. Falling back to OpenCV.")
                    self.av_container = None
                    self.v_stream = None
                    self.a_stream = None

            # 2. Fallback to OpenCV VideoWriter
            if self.writer_type != "av":
                self.writer_type = "cv2"
                fourcc = cv2.VideoWriter_fourcc(*'avc1')
                self.cv_writer = cv2.VideoWriter(self.full_path, fourcc, self.fps, (w, h))
                if not self.cv_writer.isOpened():
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    self.cv_writer = cv2.VideoWriter(self.full_path, fourcc, self.fps, (w, h))

            self.recording = True
            self.start_time = time.time()

            # Start video worker thread
            self.video_thread = threading.Thread(target=self._video_worker, daemon=True, name=f"RecVideo-{self.camera_name}")
            self.video_thread.start()

            # Start audio worker thread if PyAV audio stream exists
            if self.writer_type == "av" and self.a_stream is not None and self.audio_urls:
                self.audio_thread = threading.Thread(target=self._audio_worker, daemon=True, name=f"RecAudio-{self.camera_name}")
                self.audio_thread.start()

            logging.info(f"Recording started for '{self.camera_name}'")

    def stop(self):
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            self.stop_event.set()

        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join(timeout=3)
            self.video_thread = None

        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=3)
            self.audio_thread = None

        with self.lock:
            if self.writer_type == "av" and self.av_container is not None:
                try:
                    # Flush video
                    if self.v_stream is not None:
                        for pkt in self.v_stream.encode(None):
                            self.av_container.mux(pkt)
                    # Flush audio
                    if self.a_stream is not None:
                        for pkt in self.a_stream.encode(None):
                            self.av_container.mux(pkt)
                    self.av_container.close()
                except Exception as e:
                    logging.error(f"{self.camera_name}: Error closing PyAV recording container: {e}")
                self.av_container = None
                self.v_stream = None
                self.a_stream = None
            elif self.cv_writer is not None:
                try:
                    self.cv_writer.release()
                except Exception as e:
                    logging.error(f"{self.camera_name}: Error releasing OpenCV writer: {e}")
                self.cv_writer = None

            self.writer_type = None

        logging.info(f"Recording stopped for '{self.camera_name}' -> {self.filename}")

    def _video_worker(self):
        interval = 1.0 / self.fps
        next_tick = time.monotonic()
        v_pts = 0

        while self.recording and not self.stop_event.is_set():
            if self.frame_provider:
                try:
                    frame = self.frame_provider()
                    if frame is not None:
                        with self.lock:
                            if self.writer_type == "av" and self.av_container is not None and self.v_stream is not None:
                                av_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
                                av_frame.pts = v_pts
                                v_pts += 1
                                for pkt in self.v_stream.encode(av_frame):
                                    self.av_container.mux(pkt)
                            elif self.cv_writer is not None:
                                self.cv_writer.write(frame)
                except Exception as e:
                    logging.debug(f"{self.camera_name}: Video encode error: {e}")

            next_tick += interval
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.monotonic()

    def _audio_worker(self):
        """Demux and transcode RTSP audio packets into the MP4 container."""
        for url in self.audio_urls:
            if self.stop_event.is_set() or not self.recording:
                return

            in_container = None
            try:
                in_container = av.open(
                    url,
                    options={"rtsp_transport": "tcp", "stimeout": "4000000"},
                    timeout=5
                )
                in_audio_stream = next((s for s in in_container.streams if s.type == "audio"), None)
                if in_audio_stream is None:
                    in_container.close()
                    continue

                for packet in in_container.demux(in_audio_stream):
                    if self.stop_event.is_set() or not self.recording:
                        break
                    try:
                        for frame in packet.decode():
                            frame.pts = None
                            if self.a_resampler is not None:
                                for resampled in self.a_resampler.resample(frame):
                                    with self.lock:
                                        if self.av_container is not None and self.a_stream is not None:
                                            for out_pkt in self.a_stream.encode(resampled):
                                                self.av_container.mux(out_pkt)
                    except Exception:
                        continue

                in_container.close()
                return
            except Exception as e:
                logging.debug(f"{self.camera_name}: Audio mux worker error on {url}: {e}")
                if in_container is not None:
                    try:
                        in_container.close()
                    except Exception:
                        pass


class VideoRecorder:
    """
    Multi-Camera Video & Audio Recorder.
    Triggered manually on demand to capture individual or all cameras.
    """
    def __init__(self, settings=None, fps: int = None, recordings_dir: str = None):
        self.settings = settings or get_settings()
        self.fps = fps or getattr(self.settings, "record_fps", 15)
        self.recordings_dir = recordings_dir or self.settings.recordings_dir
        os.makedirs(self.recordings_dir, exist_ok=True)

        self.sessions = {}  # { camera_name: SingleCameraRecorder }
        self.start_time = None
        self.lock = threading.Lock()

    def start(self, camera_manager, target: str = "all"):
        """
        Start recording for all cameras or a specific camera.
        """
        with self.lock:
            cam_names = [target] if (target and target != "all") else camera_manager.get_camera_names()
            
            started_cams = []
            for name in cam_names:
                if name not in self.sessions or not self.sessions[name].recording:
                    audio_urls = self.settings.audio_candidate_urls(name)
                    provider = lambda n=name: camera_manager.build_single(n, w=1280, h=720)
                    
                    session = SingleCameraRecorder(
                        camera_name=name,
                        frame_provider=provider,
                        frame_size=(1280, 720),
                        fps=self.fps,
                        audio_urls=audio_urls,
                        recordings_dir=self.recordings_dir
                    )
                    session.start()
                    self.sessions[name] = session
                    started_cams.append(name)

            if not self.start_time:
                self.start_time = time.time()

            logging.info(f"Recording started for {started_cams}")
            return {
                "status": "started",
                "recording": True,
                "active_cameras": list(self.sessions.keys()),
                "duration_seconds": 0
            }

    def stop(self, target: str = "all"):
        """
        Stop recording for all cameras or a specific camera.
        """
        with self.lock:
            stopped_cams = []
            if target and target != "all":
                if target in self.sessions:
                    rec = self.sessions.pop(target)
                    rec.stop()
                    stopped_cams.append(target)
            else:
                for name, rec in list(self.sessions.items()):
                    rec.stop()
                    stopped_cams.append(name)
                self.sessions.clear()

            if not self.sessions:
                self.start_time = None

            logging.info(f"Recording stopped for {stopped_cams}")
            return {
                "status": "stopped",
                "recording": len(self.sessions) > 0,
                "stopped_cameras": stopped_cams,
                "active_cameras": list(self.sessions.keys())
            }

    def toggle(self, camera_manager, target: str = "all"):
        if self.is_recording(target):
            return self.stop(target=target)
        else:
            return self.start(camera_manager, target=target)

    def is_recording(self, target: str = None) -> bool:
        with self.lock:
            if target and target != "all":
                return target in self.sessions and self.sessions[target].recording
            return any(s.recording for s in self.sessions.values())

    def get_status(self):
        with self.lock:
            active_cams = [name for name, s in self.sessions.items() if s.recording]
            is_rec = len(active_cams) > 0
            dur = int(time.time() - self.start_time) if is_rec and self.start_time else 0

            return {
                "recording": is_rec,
                "active_targets": active_cams,
                "duration_seconds": dur,
                "fps": self.fps,
                "total_active": len(active_cams)
            }

    def get_recordings(self, query: str = None, target_date: str = None, target_camera: str = None):
        """
        Scan recordings directory and return list of video metadata dictionaries,
        filtered by query string, date (YYYY-MM-DD), or camera name.
        """
        results = []
        if not os.path.exists(self.recordings_dir):
            return results

        q = query.lower().strip() if query else ""

        for root, _, files in os.walk(self.recordings_dir):
            for file in sorted(files, reverse=True):
                if not file.endswith(".mp4"):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.recordings_dir).replace("\\", "/")
                parts = rel_path.split("/")

                file_date = None
                file_camera = None

                if len(parts) >= 3:
                    file_date = parts[0]
                    file_camera = parts[1]
                elif len(parts) == 2:
                    file_date = parts[0]

                try:
                    stat = os.stat(full_path)
                    mtime = stat.st_mtime
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    created_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue

                if not file_date:
                    file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

                if not file_camera:
                    for known_cam in (self.settings.cameras.keys() if hasattr(self.settings, "cameras") else []):
                        safe = "".join(c if c.isalnum() else "_" for c in known_cam).strip("_")
                        if safe in file:
                            file_camera = known_cam
                            break
                    if not file_camera:
                        file_camera = "Camera"

                # Text search filtering (Matches date, camera name, or filename)
                if q:
                    searchable_text = f"{file_date} {file_camera} {file} {created_at}".lower()
                    if q not in searchable_text:
                        continue

                # Specific filters
                if target_date and target_date != "all" and file_date != target_date:
                    continue
                if target_camera and target_camera != "all" and file_camera != target_camera:
                    continue

                results.append({
                    "filename": file,
                    "rel_path": rel_path,
                    "camera": file_camera,
                    "date": file_date,
                    "created_at": created_at,
                    "size_mb": size_mb,
                    "url": f"/video_recordings/{rel_path}"
                })

        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

    def delete_recording(self, rel_path: str) -> bool:
        safe_rel = os.path.normpath(rel_path).replace("\\", "/").lstrip("/")
        if ".." in safe_rel:
            return False

        full_path = os.path.join(self.recordings_dir, safe_rel)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            os.remove(full_path)
            parent_dir = os.path.dirname(full_path)
            try:
                if os.path.exists(parent_dir) and not os.listdir(parent_dir) and parent_dir != self.recordings_dir:
                    os.rmdir(parent_dir)
            except Exception:
                pass
            return True
        return False

    def delete_all_recordings(self, query: str = None, target_date: str = None, target_camera: str = None) -> int:
        items = self.get_recordings(query=query, target_date=target_date, target_camera=target_camera)
        deleted_count = 0
        for item in items:
            if self.delete_recording(item["rel_path"]):
                deleted_count += 1
        return deleted_count


_recorder_instance = None


def get_recorder(settings=None, fps: int = None) -> VideoRecorder:
    global _recorder_instance
    if _recorder_instance is None:
        _recorder_instance = VideoRecorder(settings=settings, fps=fps)
    return _recorder_instance
