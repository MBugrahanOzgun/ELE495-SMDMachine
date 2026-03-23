"""
File Name       : grbl.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
GRBL seri port kontrolcü (/dev/ttyACM0 — Arduino Uno R3).
Her G-code komutunu gönderir ve "ok" yanıtını bekler.
"""

import serial
import time
import threading
import re
import logging

logger = logging.getLogger("grbl")


class GrblController:
    def __init__(self, port, baud, timeout=10):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.serial = None
        self.connected = False
        self.lock = threading.Lock()
        self.state = "Disconnected"
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.alarm = False
        self.error_msg = ""
        self.on_status_change = None
        self.on_log = None

    def connect(self):
        try:
            self.serial = serial.Serial(port=self.port, baudrate=self.baud, timeout=self.timeout)
            time.sleep(2)
            self._flush()
            self.serial.write(b"\x18")
            time.sleep(1)
            self._flush()
            self.connected = True
            self.state = "Idle"
            self._log(f"GRBL bağlandı: {self.port}")
            return True
        except Exception as e:
            self.error_msg = str(e)
            self._log(f"GRBL bağlantı hatası: {e}", level="error")
            return False

    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False
        self.state = "Disconnected"
        self._log("GRBL bağlantı kesildi")

    def send_command(self, cmd, timeout=None):
        if not self.connected:
            return False, "GRBL bağlı değil"
        timeout = timeout or self.timeout
        cmd = cmd.strip()
        with self.lock:
            try:
                self._flush()
                self._log(f">> {cmd}")
                self.serial.write((cmd + "\n").encode())
                return self._wait_for_ok(timeout, cmd)
            except Exception as e:
                self.error_msg = str(e)
                self._log(f"Komut hatası: {e}", level="error")
                return False, str(e)

    def _wait_for_ok(self, timeout, cmd=""):
        start = time.time()
        lines = []
        while (time.time() - start) < timeout:
            if self.serial.in_waiting > 0:
                raw = self.serial.readline().decode("utf-8", errors="ignore").strip()
                if not raw:
                    continue
                lines.append(raw)
                self._log(f"<< {raw}")
                if raw == "ok":
                    return True, "\n".join(lines)
                if raw.startswith("error:"):
                    self.error_msg = raw
                    self._log(f"GRBL HATA: {raw}", level="error")
                    return False, raw
                if raw.startswith("ALARM:"):
                    self.alarm = True
                    self.state = "Alarm"
                    self.error_msg = raw
                    self._log(f"GRBL ALARM: {raw}", level="error")
                    return False, raw
                if raw.startswith("[PRB:"):
                    self._parse_probe(raw)
            time.sleep(0.01)
        self._log(f"TIMEOUT: '{cmd}' için ok gelmedi ({timeout}s)", level="error")
        return False, "TIMEOUT"

    def query_status(self):
        if not self.connected:
            return
        with self.lock:
            try:
                self.serial.write(b"?")
                time.sleep(0.1)
                while self.serial.in_waiting > 0:
                    raw = self.serial.readline().decode("utf-8", errors="ignore").strip()
                    if raw.startswith("<"):
                        self._parse_status(raw)
            except Exception as e:
                logger.debug(f"Status query error: {e}")

    def _parse_status(self, line):
        try:
            m = re.match(r"<(\w+)", line)
            if m:
                self.state = m.group(1)
            m = re.search(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)", line)
            if m:
                self.position = {"x": float(m.group(1)), "y": float(m.group(2)), "z": float(m.group(3))}
            if self.on_status_change:
                self.on_status_change(self.state, self.position)
        except Exception:
            pass

    def _parse_probe(self, line):
        try:
            m = re.search(r"\[PRB:([-\d.]+),([-\d.]+),([-\d.]+):(\d)\]", line)
            if m:
                self.position["z"] = float(m.group(3))
                self._log(f"Probe: Z={self.position['z']}, OK={m.group(4)=='1'}")
        except Exception:
            pass

    def soft_reset(self):
        if self.serial and self.serial.is_open:
            self.serial.write(b"\x18")
            time.sleep(1)
            self._flush()
            self.alarm = False
            self.state = "Idle"
            self._log("GRBL soft reset")

    def unlock(self):
        return self.send_command("$X")

    def hold(self):
        if self.serial and self.serial.is_open:
            self.serial.write(b"!")
            self.state = "Hold"
            self._log("Feed Hold")

    def resume(self):
        if self.serial and self.serial.is_open:
            self.serial.write(b"~")
            self._log("Resume")

    def _flush(self):
        if self.serial:
            self.serial.flushInput()
            self.serial.flushOutput()
            while self.serial.in_waiting > 0:
                self.serial.read(self.serial.in_waiting)

    def _log(self, msg, level="info"):
        getattr(logger, level, logger.info)(msg)
        if self.on_log:
            self.on_log(msg, level)
