"""
File Name       : tester.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
Test İstasyonu Kontrolcü (Arduino 2 — CH340 /dev/ttyUSB0).
Seri porttan "b" gönderir, Arduino'nun ölçüm çıktısını okur.

Arduino çıktı formatları:
─────────────────────────────────────────────
Direnç ölçümü:
  Hazir. Olcum icin 'b' gonder.
  Olcum basliyor...
  ADC=89.8 Vout=0.4391 V R2=962.8 Ohm
  Olcum bitti. Tekrar icin 'b' gonder.

  veya

  Hazir. Olcum icin 'b' gonder.
  Olcum basliyor...
  ADC=319.4  Vout=1.5613 V  R2=4.540 kOhm
  Olcum bitti. Tekrar icin 'b' gonder.

Diyot düz:
  Hazir. Olcum icin 'b' gonder.
  Olcum basliyor...
  ADC=40.5 Vout=0.1980 V R2=412.2 Ohm
  Diyot yonu DUZ

Diyot ters:
  Hazir. Olcum icin 'b' gonder.
  Olcum basliyor...
  Diyot yonu TERS
─────────────────────────────────────────────
"""

import serial
import time
import re
import threading
import logging

from config import RESISTOR_DEFS

logger = logging.getLogger("tester")


class TestStation:
    def __init__(self, port, baud, timeout=10):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.serial = None
        self.connected = False
        self.lock = threading.Lock()

        # Son ölçüm verileri
        self.last_raw_lines = []
        self.last_adc = None
        self.last_vout = None
        self.last_resistance = None    # Ohm cinsinden saklanır
        self.last_diode_dir = None     # "DUZ" veya "TERS" veya None
        self.last_component = ""
        self.last_display = ""         # Ekrana yazdırılacak özet

        self.on_log = None

    def connect(self):
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout
            )
            time.sleep(2)
            self._flush()
            self.connected = True
            self._log(f"Test istasyonu bağlandı: {self.port} @ {self.baud}")
            return True
        except Exception as e:
            self._log(f"Test istasyonu bağlantı hatası: {e}", level="error")
            return False

    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False
        self._log("Test istasyonu bağlantı kesildi")

    def measure(self):
        """
        Arduino'ya "b" gönder ve tüm yanıt satırlarını oku.

        Returns:
            dict {
                "raw_lines": [...],
                "resistance": float or None,  # Ohm
                "adc": float or None,
                "vout": float or None,
                "diode": "DUZ" | "TERS" | None,
                "display": str,
            }
        """
        if not self.connected:
            return {
                "raw_lines": [],
                "resistance": None,
                "adc": None,
                "vout": None,
                "diode": None,
                "display": "Bağlı değil"
            }

        with self.lock:
            try:
                self._flush()
                self._log(">> b (ölçüm başlatıldı)")

                # newline göndermek daha güvenli
                self.serial.write(b"b\n")
                self.serial.flush()

                lines = self._read_until_done()

                self.last_raw_lines = lines
                self._parse_lines(lines)

                return {
                    "raw_lines": lines,
                    "resistance": self.last_resistance,
                    "adc": self.last_adc,
                    "vout": self.last_vout,
                    "diode": self.last_diode_dir,
                    "display": self.last_display,
                }

            except Exception as e:
                self._log(f"Ölçüm hatası: {e}", level="error")
                return {
                    "raw_lines": [],
                    "resistance": None,
                    "adc": None,
                    "vout": None,
                    "diode": None,
                    "display": f"Hata: {e}"
                }

    def _read_until_done(self):
        """
        Satırları oku:
        - "Olcum bitti" gelirse → direnç ölçümü tamamlandı
        - "Diyot yonu DUZ" gelirse → diyot düz
        - "Diyot yonu TERS" gelirse → diyot ters
        - Timeout'a kadar oku
        """
        lines = []
        start = time.time()

        while (time.time() - start) < self.timeout:
            if self.serial.in_waiting > 0:
                raw = self.serial.readline().decode("utf-8", errors="ignore").strip()
                if not raw:
                    continue

                lines.append(raw)
                self._log(f"<< {raw}")

                if "Olcum bitti" in raw:
                    break
                if "Diyot yonu" in raw:
                    break

            time.sleep(0.02)

        if not lines:
            self._log("TIMEOUT: Test istasyonundan yanıt gelmedi", level="error")

        return lines

    def _parse_lines(self, lines):
        """
        Arduino çıktısını çözümle.

        Desteklenen örnekler:
        - ADC=89.8 Vout=0.4391 V R2=962.8 Ohm
        - ADC=319.4 Vout=1.5613 V R2=4.540 kOhm
        - Diyot yonu DUZ
        - Diyot yonu TERS
        """
        self.last_adc = None
        self.last_vout = None
        self.last_resistance = None
        self.last_diode_dir = None
        self.last_display = ""

        raw_text = " ".join(lines)

        # Diyot yönü önce kontrol edilsin
        if re.search(r"Diyot\s+yonu\s+TERS", raw_text, re.IGNORECASE):
            self.last_diode_dir = "TERS"

        elif re.search(r"Diyot\s+yonu\s+DUZ", raw_text, re.IGNORECASE):
            self.last_diode_dir = "DUZ"

        # ADC
        adc_match = re.search(r"ADC\s*=\s*([\d.]+)", raw_text, re.IGNORECASE)
        if adc_match:
            self.last_adc = float(adc_match.group(1))

        # Vout
        vout_match = re.search(r"Vout\s*=\s*([\d.]+)\s*V", raw_text, re.IGNORECASE)
        if vout_match:
            self.last_vout = float(vout_match.group(1))

        # R2
        # Hem Ohm hem kOhm desteklenir
        r2_match = re.search(
            r"R2\s*=\s*([\d.]+)\s*(k?Ohm)",
            raw_text,
            re.IGNORECASE
        )
        if r2_match:
            r_value = float(r2_match.group(1))
            r_unit = r2_match.group(2).lower()

            if r_unit == "kohm":
                self.last_resistance = r_value * 1000.0
            else:
                self.last_resistance = r_value

        # Ekran özeti
        if self.last_diode_dir == "TERS":
            self.last_display = "Diyot — TERS yön"

        elif self.last_diode_dir == "DUZ":
            self.last_display = "Diyot — DÜZ yön"

        elif self.last_resistance is not None:
            if self.last_resistance >= 1000:
                self.last_display = f"{self.last_resistance / 1000:.3f} kOhm"
            else:
                self.last_display = f"{self.last_resistance:.1f} Ohm"

        else:
            self.last_display = "Ölçüm alınamadı"

        self._log(
            f"Çözüm: ADC={self.last_adc}, "
            f"Vout={self.last_vout}, "
            f"R={self.last_resistance}, "
            f"Diyot={self.last_diode_dir}, "
            f"Gösterim={self.last_display}"
        )

    def identify_component(self, measure_result, placed_components):
        """
        Ölçüm sonucuna göre hangi komponent olduğunu belirle.

        Args:
            measure_result: measure() fonksiyonunun döndürdüğü dict
            placed_components: Zaten yerleştirilmiş komponentlerin set'i

        Returns:
            (comp_name: str, comp_type: str)
            comp_type: "resistor", "diode", "diode_reversed", "unknown"
        """
        diode = measure_result.get("diode")
        resistance = measure_result.get("resistance")

        # Diyot ters
        if diode == "TERS":
            if "D1" not in placed_components:
                return "D1", "diode_reversed"
            elif "D2" not in placed_components:
                return "D2", "diode_reversed"
            else:
                return "D_EXTRA", "unknown"

        # Diyot düz
        if diode == "DUZ":
            if "D1" not in placed_components:
                return "D1", "diode"
            elif "D2" not in placed_components:
                return "D2", "diode"
            else:
                return "D_EXTRA", "unknown"

        # Direnç
        if resistance is not None:
            for rname, rdef in RESISTOR_DEFS.items():
                if rname in placed_components:
                    continue

                if rdef["min"] <= resistance <= rdef["max"]:
                    self.last_component = rname
                    self._log(f"Komponent tanımlandı: {rname} ({resistance} Ohm)")
                    return rname, "resistor"

            self._log(
                f"Direnç değeri hiçbir tanıma uymuyor: {resistance} Ohm",
                level="warning"
            )
            return "UNKNOWN", "unknown"

        self._log("Ölçüm sonucu çözümlenemedi", level="error")
        return "UNKNOWN", "unknown"

    def wait_for_rotation(self):
        """
        Diyot döndürme sonrası Arduino'dan onay bekle.
        """
        self._log("Diyot 180° döndürülüyor, bekleniyor...")
        start = time.time()

        while (time.time() - start) < 15:
            if self.serial and self.serial.in_waiting > 0:
                raw = self.serial.readline().decode("utf-8", errors="ignore").strip()
                self._log(f"<< {raw}")

                if "OK" in raw.upper() or "Hazir" in raw or "bitti" in raw.lower():
                    self._log("Diyot döndürme tamamlandı")
                    return True

            time.sleep(0.1)

        self._log("TIMEOUT: Diyot döndürme yanıtı gelmedi", level="error")
        return False

    def _flush(self):
        if self.serial:
            try:
                self.serial.reset_input_buffer()
                self.serial.reset_output_buffer()
            except Exception:
                self.serial.flushInput()
                while self.serial.in_waiting > 0:
                    self.serial.read(self.serial.in_waiting)

    def _log(self, msg, level="info"):
        getattr(logger, level, logger.info)(msg)
        if self.on_log:
            self.on_log(msg, level)
