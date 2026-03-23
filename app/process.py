"""
File Name       : process.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
Pick & Place ana süreç kontrolcüsü.
Z ekseni: aşağı G1 Z-20 F200, yukarı G0 Z15.
Test istasyonunda aşağı inip ölçüm yapar.
"""

import time
import threading
import logging

from config import (
    INIT_SEQUENCE, COMPONENT_SLOTS, TEST_STATION,
    SAFE_Z, PICK_Z, PLACE_Z, TEST_Z, Z_FEED,
    TEST_DWELL_SECONDS, PCB_POSITIONS,
    GRBL_OK_TIMEOUT
)

logger = logging.getLogger("process")


class PickAndPlaceProcess:
    def __init__(self, grbl, tester, socketio, camera=None, yolo=None):
        self.grbl = grbl
        self.tester = tester
        self.socketio = socketio
        self.camera = camera
        self.yolo = yolo

        self.running = False
        self.paused = False
        self.stop_requested = False
        self.current_step = ""
        self.current_slot = 0

        self.placed_components = {}
        self.measurements = {}
        self.errors = []

        # Görüntü işleme
        self.last_detection = None
        self.last_placement_verify = None
        self.detection_history = []

        # Test istasyonu son verileri
        self.last_test_data = {}

        self._thread = None

    def start(self):
        if self.running:
            self._emit_log("Proses zaten çalışıyor!", "warning")
            return False
        self.running = True
        self.stop_requested = False
        self.paused = False
        self.placed_components = {}
        self.measurements = {}
        self.errors = []
        self.detection_history = []
        self.last_test_data = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._emit_log("▶ Proses başlatıldı")
        return True

    def stop(self):
        self.stop_requested = True
        self.running = False
        self.grbl.hold()
        self._emit_log("⏹ Proses durduruldu!", "warning")
        self._emit_state()

    def pause(self):
        self.paused = True
        self.grbl.hold()
        self._emit_log("⏸ Proses duraklatıldı")
        self._emit_state()

    def resume(self):
        self.paused = False
        self.grbl.resume()
        self._emit_log("▶ Proses devam ediyor")
        self._emit_state()

    # ── Z Hareketleri ───────────────────────────────────────────────

    def _z_down(self, z_val):
        """Aşağı: G1 kontrollü, yavaş"""
        return self._send_gcode(f"G1 Z{z_val} F{Z_FEED}")

    def _z_up(self):
        """Yukarı: G0 hızlı, güvenli yükseklik"""
        return self._send_gcode(f"G0 Z{SAFE_Z}")

    # ── Ana Süreç ───────────────────────────────────────────────────

    def _run(self):
        try:
            # 1) Başlatma
            if not self._do_init():
                self._finish("Başlatma hatası!")
                return

            # 2) 8 slot döngüsü
            for slot in COMPONENT_SLOTS:
                if self.stop_requested:
                    break
                self._wait_while_paused()

                self.current_slot = slot["index"]
                self._emit_log(f"━━━ Slot {slot['index']}/8 ━━━")
                self._emit_state()

                # A) Komponenti al
                if not self._pick_component(slot):
                    self._finish(f"Slot {slot['index']} alma hatası!")
                    return

                # B) Kamera tespiti (pick sonrası)
                self._do_vision_check(f"PICK slot {slot['index']}")

                # C) Test istasyonuna götür, aşağı in, ölç
                result = self._test_component(slot["index"])
                if result is None:
                    self._finish(f"Slot {slot['index']} test hatası!")
                    return

                comp_name, comp_type, display_val = result

                # D) Diyot ters ise → döndür
                if comp_type == "diode_reversed":
                    self._emit_log(f"⚠ {comp_name} TERS! Döndürülüyor...")
                    if not self._handle_diode_reversal():
                        self._finish(f"{comp_name} döndürme hatası!")
                        return
                    comp_type = "diode"

                # E) Tanımlanamadı
                if comp_name == "UNKNOWN":
                    self._emit_log(f"❌ Slot {slot['index']}: Tanımlanamadı ({display_val})", "error")
                    self.errors.append(f"Slot {slot['index']}: Tanımlanamadı")
                    self._z_up()
                    self._send_gcode("M9")
                    continue

                # F) PCB'de yeri var mı kontrol et
                if comp_name not in PCB_POSITIONS:
                    self._emit_log(
                        f"📋 {comp_name} tanımlandı — PCB'de yeri yok, "
                        f"slota geri bırakılacak ({display_val})"
                    )
                    self.measurements[comp_name] = display_val

                    # Ölçüm sonucunu ekrana yaz
                    self.socketio.emit("component_placed", {
                        "name": comp_name,
                        "value": display_val + " ✓ ölçüldü"
                    })

                    # Alındığı slota geri götür ve bırak
                    ok, _ = self._z_up()
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return
                    ok, _ = self._send_gcode(f"G0 X{slot['x']} Y{slot['y']}")
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return
                    ok, _ = self._z_down(PLACE_Z)
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return
                    ok, _ = self._send_gcode("M9")   # vakum kapat
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return
                    ok, _ = self._send_gcode("G4 P0.5")
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return
                    ok, _ = self._z_up()
                    if not ok:
                        self._finish(f"{comp_name} geri bırakma hatası!")
                        return

                    self._emit_log(
                        f"✅ {comp_name} ölçüldü ({display_val}) → "
                        f"Slot {slot['index']}'e geri bırakıldı"
                    )
                    continue

                # G) PCB'ye yerleştir
                if not self._place_component(comp_name):
                    self._finish(f"{comp_name} yerleştirme hatası!")
                    return

                # H) Yerleştirme doğrulama
                self._do_placement_check(comp_name)

                # I) Sonuç kaydet
                self.placed_components[comp_name] = True
                self.measurements[comp_name] = display_val
                self._emit_component_placed(comp_name, display_val)
                self._emit_log(f"✅ {comp_name} yerleştirildi ({display_val})")

            # 3) Bitir
            self._z_up()
            self._send_gcode("G0 X0 Y0")
            msg = "Tüm komponentler tamamlandı!" if not self.stop_requested else "Proses durduruldu"
            self._finish(msg)

        except Exception as e:
            logger.exception("Process error")
            self._finish(f"Beklenmeyen hata: {e}")

    # ── Alt Süreçler ────────────────────────────────────────────────

    def _do_init(self):
        self.current_step = "Başlatma"
        self._emit_state()
        self._emit_log("🔧 Başlatma sekansı...")
        for cmd in INIT_SEQUENCE:
            if self.stop_requested:
                return False
            ok, _ = self._send_gcode(cmd)
            if not ok:
                return False
        self._emit_log("✅ Başlatma tamamlandı")
        return True

    def _pick_component(self, slot):
        """Slot'tan komponent al: Z15→XY→G1 Z-20 F200→M8→G0 Z15"""
        self.current_step = f"Slot {slot['index']} alınıyor"
        self._emit_state()
        self._emit_log(f"📦 Slot {slot['index']} — X{slot['x']} Y{slot['y']}")

        ok, _ = self._z_up()
        if not ok:
            return False
        ok, _ = self._send_gcode(f"G0 X{slot['x']} Y{slot['y']}")
        if not ok:
            return False
        ok, _ = self._z_down(PICK_Z)
        if not ok:
            return False
        ok, _ = self._send_gcode("M8")       # vakum aç
        if not ok:
            return False
        ok, _ = self._send_gcode("G4 P0.5")  # vakum oturması
        if not ok:
            return False
        ok, _ = self._z_up()
        if not ok:
            return False
        return True

    def _test_component(self, slot_index):
        """
        Test istasyonuna git, aşağı in, bekle, ölç, tanımla.
        Returns: (comp_name, comp_type, display_val) veya None
        """
        self.current_step = f"Slot {slot_index} test ediliyor"
        self._emit_state()

        # Test istasyonuna git
        ok, _ = self._send_gcode(f"G0 X{TEST_STATION['x']} Y{TEST_STATION['y']}")
        if not ok:
            return None

        # 1) Aşağı in (G1 kontrollü) — temas
        ok, _ = self._z_down(TEST_Z)
        if not ok:
            return None

        # 2) İlk temas sonrası bekle
        ok, _ = self._send_gcode(f"G4 P{TEST_DWELL_SECONDS}")
        if not ok:
            return None

        # 3) Yukarı çık (G0 Z15 hızlı)
        ok, _ = self._z_up()
        if not ok:
            return None

        # 4) Yukarıda bekle
        ok, _ = self._send_gcode(f"G4 P{TEST_DWELL_SECONDS}")
        if not ok:
            return None

        # 5) Yavaşça tekrar aşağı in
        ok, _ = self._z_down(TEST_Z)
        if not ok:
            return None

        # 5.1) Temasın oturması için ek kısa bekleme
        ok, _ = self._send_gcode("G4 P1.0")
        if not ok:
            return None

        # 6) Ölçüm yap
        self._emit_log("🔬 Ölçüm yapılıyor...")
        data = self.tester.measure()
        self.last_test_data = data

        # Debug log
        self._emit_log(
            f"TEST DATA -> display={data.get('display')} "
            f"R={data.get('resistance')} "
            f"ADC={data.get('adc')} "
            f"Vout={data.get('vout')} "
            f"diode={data.get('diode')}"
        )

        # Ölçüm sonuçlarını arayüze gönder
        self.socketio.emit("test_measurement", {
            "slot": slot_index,
            "display": data["display"],
            "resistance": data["resistance"],
            "adc": data["adc"],
            "vout": data["vout"],
            "diode": data["diode"],
            "raw_lines": data["raw_lines"],
        })

        display_val = data["display"]
        self._emit_log(f"📏 Ölçüm: {display_val}")
        self._emit_measurement(slot_index, display_val)

        # Ölçüm hiç parse edilemediyse uyarı düş
        if data.get("resistance") is None and data.get("diode") is None:
            self._emit_log("⚠ Ölçüm parse edilemedi", "warning")

        # Yukarı çık (test bitti)
        ok, _ = self._z_up()
        if not ok:
            return None

        # Tanımla
        comp_name, comp_type = self.tester.identify_component(
            data, set(self.placed_components.keys())
        )
        self._emit_log(f"🏷 Tanımlanan: {comp_name} ({comp_type})")

        return comp_name, comp_type, display_val

    def _handle_diode_reversal(self):
        """Diyot ters: bırak → kısa süre dönmesini bekle → hemen tekrar al"""
        # Test istasyonuna git
        ok, _ = self._send_gcode(f"G0 X{TEST_STATION['x']} Y{TEST_STATION['y']}")
        if not ok:
            return False

        # Aşağı in
        ok, _ = self._z_down(TEST_Z)
        if not ok:
            return False

        # Diyotu bırak
        ok, _ = self._send_gcode("M9")
        if not ok:
            return False

        self._emit_log("🔄 Diyot bırakıldı, test istasyonu dönüyor...")

        # Test istasyonunun fiziksel dönme süresi ~3 saniye
        # Gerekirse 3.2 / 3.5 / 3.8 diye ayarlayabilirsin
        time.sleep(5.5)

        self._emit_log("🤏 Döndürme tamamlandı, diyot geri alınıyor...")

        # Hemen geri al
        ok, _ = self._send_gcode("M8")
        if not ok:
            return False

        ok, _ = self._send_gcode("G4 P0.5")
        if not ok:
            return False

        # Yukarı kalk
        ok, _ = self._z_up()
        if not ok:
            return False

        self._emit_log("✅ Diyot döndürüldü ve alındı")
        return True

    def _place_component(self, comp_name):
        """PCB'ye yerleştir: Z15→XY→G1 Z-20 F200→M9→G0 Z15"""
        self.current_step = f"{comp_name} yerleştiriliyor"
        self._emit_state()

        pos = PCB_POSITIONS.get(comp_name)
        if not pos:
            self._emit_log(f"❌ {comp_name} PCB pozisyonu tanımlı değil!", "error")
            return False

        self._emit_log(f"📍 {comp_name} → X{pos['x']} Y{pos['y']}")

        ok, _ = self._z_up()
        if not ok:
            return False
        ok, _ = self._send_gcode(f"G0 X{pos['x']} Y{pos['y']}")
        if not ok:
            return False
        ok, _ = self._z_down(PLACE_Z)
        if not ok:
            return False
        ok, _ = self._send_gcode("M9")       # vakum kapat
        if not ok:
            return False
        ok, _ = self._send_gcode("G4 P0.5")
        if not ok:
            return False
        ok, _ = self._z_up()
        if not ok:
            return False
        return True

    # ── Görüntü İşleme ─────────────────────────────────────────────

    def _do_vision_check(self, label=""):
        if not self.camera or not self.yolo or not self.yolo.is_ready():
            return
        try:
            frame = self.camera.get_frame()
            if frame is None:
                return
            dets = self.yolo.detect(frame)
            if dets:
                top = dets[0]
                det_info = {
                    "label": label,
                    "class": top.class_name,
                    "score": round(top.score, 3),
                    "box": top.box,
                    "total_detections": len(dets),
                    "time": time.strftime("%H:%M:%S"),
                }
                self.last_detection = det_info
                self.detection_history.append(det_info)
                self._emit_log(f"📷 Tespit: {top.class_name} (%{top.score*100:.1f})")
                self.socketio.emit("vision_detection", det_info)
            else:
                self._emit_log("📷 Tespit: bulunamadı", "warning")
        except Exception as e:
            logger.debug(f"Vision check error: {e}")

    def _do_placement_check(self, comp_name):
        if not self.camera or not self.yolo or not self.yolo.is_ready():
            return
        try:
            from vision.placement_verify import verify_placement
            frame = self.camera.get_frame()
            if frame is None:
                return
            dets = self.yolo.detect(frame)
            if not dets:
                result = {"pad": comp_name, "status": "NO_DETECTION", "accuracy": 0.0}
            else:
                top = dets[0]
                result = verify_placement(comp_name, top.box, tolerance_px=30)
                pcb_pos = PCB_POSITIONS.get(comp_name)
                if pcb_pos:
                    target = [
                        int(pcb_pos["x"]) - 15,
                        int(pcb_pos["y"]) - 15,
                        int(pcb_pos["x"]) + 15,
                        int(pcb_pos["y"]) + 15
                    ]
                    scores = self.yolo.score_targets([target], [d.box for d in dets])
                    if scores:
                        result["iou"] = scores[0]["iou"]
                        result["error_pct"] = scores[0]["error_pct"]
            self.last_placement_verify = result
            self.socketio.emit("placement_verify", result)
            self._emit_log(
                f"🎯 Doğrulama: {comp_name} → {result.get('status', '?')} "
                f"(%{result.get('accuracy', 0):.1f})"
            )
        except Exception as e:
            logger.debug(f"Placement check error: {e}")

    # ── Yardımcı ────────────────────────────────────────────────────

    def _send_gcode(self, cmd):
        ok, resp = self.grbl.send_command(cmd, timeout=GRBL_OK_TIMEOUT)
        if not ok:
            self._emit_log(f"❌ GRBL: {cmd} → {resp}", "error")
            self.errors.append(f"GRBL: {cmd} → {resp}")
        self.grbl.query_status()
        self._emit_position()
        return ok, resp

    def _wait_while_paused(self):
        while self.paused and not self.stop_requested:
            time.sleep(0.1)

    def _finish(self, message):
        self.running = False
        self.current_step = "Bitti"
        self._emit_log(f"🏁 {message}")
        self._emit_state()
        self.socketio.emit("process_finished", {
            "message": message,
            "placed": self.placed_components,
            "errors": self.errors
        })

    def _emit_state(self):
        self.socketio.emit("state_update", {
            "running": self.running,
            "paused": self.paused,
            "current_step": self.current_step,
            "current_slot": self.current_slot,
            "grbl_state": self.grbl.state,
            "placed": self.placed_components,
            "measurements": self.measurements,
        })

    def _emit_position(self):
        self.socketio.emit("position_update", self.grbl.position)

    def _emit_log(self, msg, level="info"):
        logger.info(msg)
        self.socketio.emit("log", {
            "message": msg,
            "level": level,
            "time": time.strftime("%H:%M:%S")
        })

    def _emit_measurement(self, slot_index, raw_value):
        self.socketio.emit("measurement", {
            "slot": slot_index,
            "value": str(raw_value)
        })

    def _emit_component_placed(self, comp_name, value):
        self.socketio.emit("component_placed", {
            "name": comp_name,
            "value": str(value)
        })
