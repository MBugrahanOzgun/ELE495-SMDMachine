#!/usr/bin/env python3
"""
File Name       : camera_server.py
Project         : CNC Pick & Place Kontrol Sistemi
Description     : rpicam-vid tabanlı MJPEG stream server.
                  Host'ta çalışır, port 5001'den stream yayınlar.
                  Docker container bu stream'i kullanır.
"""
import subprocess, threading, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer

# Başlangıçta /dev/video0'ı tutan process'leri serbest bırak
os.system("fuser -k /dev/video0 2>/dev/null")
time.sleep(2)

lock = threading.Lock()
latest_frame = None


def capture_loop():
    global latest_frame
    cmd = [
        "rpicam-vid",
        "--codec", "mjpeg",
        "--width", "640",
        "--height", "480",
        "--framerate", "15",
        "--timeout", "0",
        "--nopreview",
        "-o", "-"
    ]
    while True:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            buf = b""
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    end   = buf.find(b"\xff\xd9")
                    if start != -1 and end != -1 and end > start:
                        frame = buf[start:end+2]
                        with lock:
                            latest_frame = frame
                        buf = buf[end+2:]
                    else:
                        break
        except Exception:
            pass
        # rpicam-vid çökerse /dev/video0'ı tekrar serbest bırak ve yeniden başlat
        os.system("fuser -k /dev/video0 2>/dev/null")
        time.sleep(2)


threading.Thread(target=capture_loop, daemon=True).start()
time.sleep(5)  # rpicam-vid'in başlaması için bekle


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/snapshot":
            with lock:
                frame = latest_frame
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_response(503)
                self.end_headers()

        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    with lock:
                        frame = latest_frame
                    if frame:
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + frame + b"\r\n"
                        )
                    time.sleep(0.066)
            except Exception:
                pass

        else:
            self.send_response(404)
            self.end_headers()


print("Camera server başlatılıyor: http://0.0.0.0:5001")
HTTPServer(("0.0.0.0", 5001), Handler).serve_forever()
