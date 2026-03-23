"""
File Name       : camera_service.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Description     : Host'taki rpicam-vid stream'den kamera görüntüsü alır.
"""

import cv2
import time
import threading
import logging
import urllib.request

logger = logging.getLogger("camera")

CAMERA_SERVER_URL = "http://172.17.0.1:5001"


class CameraService:
    def __init__(self, demo_mode=True, device_index=0):
        self.demo_mode = demo_mode
        self.device_index = device_index
        self.lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

    def open(self):
        try:
            urllib.request.urlopen(
                f"{CAMERA_SERVER_URL}/snapshot", timeout=3
            )
            self._running = True
            self._thread = threading.Thread(
                target=self._capture_loop, daemon=True
            )
            self._thread.start()
            logger.info("Kamera stream bağlandı")
            return True
        except Exception as e:
            logger.error(f"Kamera bağlantı hatası: {e}")
            return False

    def close(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _capture_loop(self):
        stream_url = f"{CAMERA_SERVER_URL}/stream"
        while self._running:
            try:
                cap = cv2.VideoCapture(stream_url)
                while self._running and cap.isOpened():
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        with self.lock:
                            self._frame = frame
                    else:
                        break
                cap.release()
            except Exception as e:
                logger.debug(f"Stream hatası: {e}")
            time.sleep(1)

    def get_frame(self):
        with self.lock:
            return self._frame.copy() if self._frame is not None else None

    def get_jpeg(self, quality=80):
        frame = self.get_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        return buf.tobytes() if ok else None

    def is_open(self):
        return self._running and self._frame is not None
