"""A separate CPU preview; its frames never stand in for NVIDIA evidence."""

import io
import threading
import time


class Preview:
    def __init__(self):
        self.jpeg = None
        self.frame_number = 0
        self.last_frame_at = 0
        self.error = None
        self.metadata = {}
        self._stop = threading.Event()
        self._thread = None

    def start(self, uri):
        self.stop()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._decode, args=(uri, self._stop), daemon=True, name="cctv-preview")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)
            if self._thread.is_alive():
                raise RuntimeError("Camera preview did not stop.")

    def status(self):
        return {"connected": self.jpeg is not None and time.time() - self.last_frame_at < 8,
                "last_frame_at": self.last_frame_at or None, "error": self.error, **self.metadata}

    def _decode(self, uri, stop):
        import av

        while not stop.is_set():
            try:
                with av.open(uri, options={"rtsp_transport": "tcp"}, timeout=(5, 5)) as media:
                    video = media.streams.video[0]
                    video.thread_type = "AUTO"
                    self.metadata = {"width": video.width, "height": video.height, "preview_fps": 4}
                    last_encoded = 0
                    for frame in media.decode(video=0):
                        if stop.is_set():
                            return
                        if time.monotonic() - last_encoded < 0.25:
                            continue
                        image = frame.to_image()
                        image.thumbnail((960, 540))
                        output = io.BytesIO()
                        image.save(output, format="JPEG", quality=78)
                        self.jpeg = output.getvalue()
                        self.last_frame_at = time.time()
                        self.frame_number += 1
                        self.error = None
                        last_encoded = time.monotonic()
                    self.error = "Camera stopped sending video. Reconnecting…"
            except Exception:
                if not stop.is_set():
                    self.error = "Couldn't show live video. Check the camera connection. Retrying…"
            stop.wait(2)
