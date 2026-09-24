import os
import io
import time
import logging
import threading
from src.config.settings import get_settings

try:
    import av
    AV_AVAILABLE = True
except Exception:
    av = None
    AV_AVAILABLE = False


class AudioStreamer:
    """
    Real-time RTSP-to-Browser Audio Transcoder and Streamer.
    Transcodes camera audio (G.711u / pcm_mulaw) into standard MP3 streams
    playable directly by modern web browsers via HTML5 <audio>.
    """
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._capabilities_cache = {}  # { cam_name: bool }
        self._lock = threading.Lock()

    def has_audio(self, cam_name: str) -> bool:
        """Check if camera has an active audio track."""
        if cam_name in self._capabilities_cache:
            return self._capabilities_cache[cam_name]

        urls = self.settings.audio_candidate_urls(cam_name)
        if not urls or not AV_AVAILABLE:
            self._capabilities_cache[cam_name] = False
            return False

        for url in urls:
            try:
                container = av.open(url, options={"rtsp_transport": "tcp", "stimeout": "3000000"}, timeout=3)
                audio_stream = next((s for s in container.streams if s.type == "audio"), None)
                container.close()
                if audio_stream is not None:
                    self._capabilities_cache[cam_name] = True
                    return True
            except Exception:
                pass

        self._capabilities_cache[cam_name] = False
        return False

    def generate_mp3_stream(self, cam_name: str):
        """
        Continuous generator yielding live MP3 audio bytes for HTTP chunked streaming.
        Compatible with HTML5 <audio> elements.
        """
        if not AV_AVAILABLE or not getattr(self.settings, "audio_enabled", True):
            logging.warning("Audio streaming requested but PyAV or audio is disabled.")
            return

        urls = self.settings.audio_candidate_urls(cam_name)
        if not urls:
            logging.warning(f"No RTSP audio URLs configured for {cam_name}")
            return

        while True:
            connected = False
            for url in urls:
                container = None
                try:
                    container = av.open(
                        url,
                        options={"rtsp_transport": "tcp", "stimeout": "5000000"},
                        timeout=5
                    )
                    audio_stream = next((s for s in container.streams if s.type == "audio"), None)
                    if audio_stream is None:
                        container.close()
                        continue

                    # Custom in-memory buffer for real-time MP3 muxing
                    buf = io.BytesIO()
                    out_container = av.open(buf, mode='w', format='mp3')
                    out_stream = out_container.add_stream('mp3', rate=16000)
                    out_stream.bit_rate = 32000

                    # Resample to 16kHz mono s16p for standard MP3 compliance
                    resampler = av.audio.resampler.AudioResampler(
                        format='s16p',
                        layout='mono',
                        rate=16000
                    )

                    logging.info(f"Live MP3 audio stream opened for '{cam_name}' ({audio_stream.codec_context.name})")
                    connected = True
                    self._capabilities_cache[cam_name] = True

                    for packet in container.demux(audio_stream):
                        try:
                            for frame in packet.decode():
                                frame.pts = None
                                for resampled in resampler.resample(frame):
                                    for out_packet in out_stream.encode(resampled):
                                        out_container.mux(out_packet)
                        except Exception:
                            continue

                        # Yield MP3 audio chunks when buffer has encoded packets (~2KB)
                        if buf.tell() >= 1500:
                            data = buf.getvalue()
                            buf.seek(0)
                            buf.truncate(0)
                            yield data

                    # End of demux loop
                    container.close()
                    break

                except Exception as e:
                    logging.debug(f"Audio stream interruption on '{cam_name}': {e}")
                    if container is not None:
                        try:
                            container.close()
                        except Exception:
                            pass

            if not connected:
                # Camera has no audio or is temporarily unreachable
                self._capabilities_cache[cam_name] = False
                time.sleep(2.0)


# Backwards compatibility alias
AudioPlayer = AudioStreamer

_audio_streamer_instance = None


def get_audio_player(settings=None) -> AudioStreamer:
    global _audio_streamer_instance
    if _audio_streamer_instance is None:
        _audio_streamer_instance = AudioStreamer(settings)
    return _audio_streamer_instance
