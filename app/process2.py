import time
import re
import logging

logger = logging.getLogger("tester")


class ComponentTester:
    def __init__(self, ser):
        self.ser = ser

    def measure(self, timeout=5.0):
        """
        Arduino'ya 'b' gönderir, serial çıktıyı toplar ve parse eder.

        Beklenen çıktılar:
        1) Direnç:
           Hazir. Olcum icin 'b' gonder.
           Olcum basliyor...
           ADC=319.4  Vout=1.5613 V  R2=4.540 kOhm
           Olcum bitti. Tekrar icin 'b' gonder.

        2) Diyot:
           Hazir. Olcum icin 'b' gonder.
           Olcum basliyor...
           Diyot yonu TERS
        """

        data = {
            "display": "Ölçüm alınamadı",
            "resistance": None,   # ohm cinsinden
            "adc": None,
            "vout": None,
            "diode": None,        # None / "forward" / "reversed"
            "raw_lines": [],
        }

        try:
            # Eski verileri temizle
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            # Ölçüm komutu gönder
            self.ser.write(b"b\n")
            self.ser.flush()

            start = time.time()
            raw_lines = []

            while time.time() - start < timeout:
                try:
                    line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                except Exception:
                    line = ""

                if not line:
                    continue

                raw_lines.append(line)
                logger.info(f"SERIAL << {line}")

                # Direnç ölçümü bittiyse çık
                if "Olcum bitti" in line:
                    break

                # Diyot satırı geldiyse de çıkabiliriz
                if "Diyot yonu" in line:
                    break

            data["raw_lines"] = raw_lines
            raw_text = " ".join(raw_lines)

            # -----------------------------
            # 1) Diyot kontrolü
            # -----------------------------
            if re.search(r"Diyot\s+yonu\s+TERS", raw_text, re.IGNORECASE):
                data["diode"] = "reversed"
                data["display"] = "Diyot (TERS)"
                return data

            if re.search(r"Diyot", raw_text, re.IGNORECASE):
                data["diode"] = "forward"
                data["display"] = "Diyot"
                return data

            # -----------------------------
            # 2) ADC parse
            # -----------------------------
            m_adc = re.search(r"ADC\s*=\s*([0-9]+(?:\.[0-9]+)?)", raw_text, re.IGNORECASE)
            if m_adc:
                data["adc"] = float(m_adc.group(1))

            # -----------------------------
            # 3) Vout parse
            # -----------------------------
            m_vout = re.search(r"Vout\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*V", raw_text, re.IGNORECASE)
            if m_vout:
                data["vout"] = float(m_vout.group(1))

            # -----------------------------
            # 4) R2 parse
            #    Örnek: R2=4.540 kOhm
            # -----------------------------
            m_r = re.search(
                r"R2\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(k?Ohm)",
                raw_text,
                re.IGNORECASE
            )
            if m_r:
                value = float(m_r.group(1))
                unit = m_r.group(2).lower()

                if unit == "kohm":
                    resistance_ohm = value * 1000.0
                else:
                    resistance_ohm = value

                data["resistance"] = resistance_ohm

                if resistance_ohm >= 1000:
                    data["display"] = f"{resistance_ohm / 1000.0:.3f} kOhm"
                else:
                    data["display"] = f"{resistance_ohm:.1f} Ohm"

                return data

            # Buraya geldiyse ölçüm parse edilemedi
            return data

        except Exception as e:
            logger.exception("measure() error")
            data["display"] = f"Ölçüm hatası: {e}"
            return data

    def identify_component(self, data, already_placed=None):
        """
        Parse edilmiş ölçüm verisine göre komponenti sınıflandırır.
        Burada isimlendirmeyi kendi PCB_POSITIONS yapına göre özelleştirebilirsin.
        """

        if already_placed is None:
            already_placed = set()

        # 1) Diyot öncelikli
        if data.get("diode") == "reversed":
            # Process içinde zaten diode_reversed görünce döndürme yapıyorsun
            if "D1" not in already_placed:
                return "D1", "diode_reversed"
            return "UNKNOWN", "diode_reversed"

        if data.get("diode") == "forward":
            if "D1" not in already_placed:
                return "D1", "diode"
            return "UNKNOWN", "diode"

        # 2) Direnç
        resistance = data.get("resistance")
        if resistance is not None:
            resistance_k = resistance / 1000.0

            # Burayı kendi direnç listene göre genişlet
            resistor_map = [
                ("R1", 1.0),
                ("R2", 4.7),
                ("R3", 10.0),
                ("R4", 47.0),
                ("R5", 100.0),
            ]

            tolerance = 0.30  # %30 tolerans, istersen düşürürsün
            best_name = None
            best_diff = None

            for name, nominal_k in resistor_map:
                if name in already_placed:
                    continue

                diff = abs(resistance_k - nominal_k)
                if diff <= nominal_k * tolerance:
                    if best_diff is None or diff < best_diff:
                        best_diff = diff
                        best_name = name

            if best_name:
                return best_name, "resistor"

            return "UNKNOWN", "resistor"

        # 3) Hiçbiri değilse
        return "UNKNOWN", "unknown"
