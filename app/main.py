"""
File Name       : main.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
Flask + Flask-SocketIO web sunucu.
Hata hesabı: tespit bbox'ı target box içinde mi kontrolü (piksel bazlı).
"""

import os, sys, time, logging
from flask import Flask, render_template, jsonify, Response
from flask_socketio import SocketIO

from config import (
    GRBL_PORT, GRBL_BAUD, TESTER_PORT, TESTER_BAUD,
    COMPONENT_SLOTS, TEST_STATION, PCB_POSITIONS, RESISTOR_DEFS,
    CAMERA_DEMO_MODE, CAMERA_DEVICE,
    ONNX_MODEL_PATH, ONNX_CONF_THRESHOLD, ONNX_IMG_SIZE,
)
from grbl import GrblController
from tester import TestStation
from camera_service import CameraService
from vision.yolo_runtime import YoloRuntime
from vision.placement_verify import verify_placement, PAD_PIXEL_CENTER
from process import PickAndPlaceProcess

# ── inference2.py / inference.py import ─────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vision"))
detector = None
try:
    from inference2 import ResistorDiodeDetectionONNX as _Det
    detector = _Det(capture_index=0, model_path=ONNX_MODEL_PATH)
    logging.getLogger("main").info("inference2.py detector hazır")
except Exception:
    try:
        from inference import ResistorDiodeDetectionONNX as _Det
        detector = _Det(capture_index=0)
        logging.getLogger("main").info("inference.py detector hazır (fallback)")
    except Exception as e:
        logging.getLogger("main").warning(
            f"Detector yüklenemedi, YoloRuntime kullanılacak: {e}"
        )
        detector = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("main")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "cnc-pick-place-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Donanım ─────────────────────────────────────────────────────────
grbl    = GrblController(GRBL_PORT, GRBL_BAUD)
tester  = TestStation(TESTER_PORT, TESTER_BAUD)
camera  = CameraService(demo_mode=CAMERA_DEMO_MODE, device_index=CAMERA_DEVICE)
yolo    = YoloRuntime(model_path=ONNX_MODEL_PATH, imgsz=ONNX_IMG_SIZE, conf_thres=ONNX_CONF_THRESHOLD)
process = PickAndPlaceProcess(grbl, tester, socketio, camera=camera, yolo=yolo)

_CLS_NAMES = {0: "resistor", 1: "diode"}

# ── Target box'lar piksel koordinatlarından (placement_verify ile aynı) ──
# PAD_PIXEL_CENTER: {"R1": (200,180), "R2": (200,300), "D1": (440,180), "D2": (440,300)}
PAD_BOX_HALF = 30  # ±30px target kutusu

def _build_pixel_targets():
    """
    PAD_PIXEL_CENTER'dan target box'ları oluşturur.
    Makine koordinatı değil, kamera piksel koordinatı kullanılır.
    """
    areas     = []
    pad_names = []
    for name, (px, py) in PAD_PIXEL_CENTER.items():
        areas.append([px - PAD_BOX_HALF, py - PAD_BOX_HALF,
                      px + PAD_BOX_HALF, py + PAD_BOX_HALF])
        pad_names.append(name)
    return areas, pad_names


def _check_inside_target(det_box, target_box):
    """
    Tespit bbox merkezi target box içinde mi?
    Returns: (inside: bool, distance_px: float, accuracy: float)
    """
    import math
    cx = (det_box[0] + det_box[2]) / 2
    cy = (det_box[1] + det_box[3]) / 2
    tx1, ty1, tx2, ty2 = target_box
    tcx = (tx1 + tx2) / 2
    tcy = (ty1 + ty2) / 2
    dist   = math.sqrt((cx - tcx)**2 + (cy - tcy)**2)
    inside = (tx1 <= cx <= tx2) and (ty1 <= cy <= ty2)
    acc    = max(0.0, 100.0 * (1.0 - dist / (2.0 * PAD_BOX_HALF)))
    return inside, round(dist, 2), round(acc, 2)


def _ts():
    return time.strftime("%H:%M:%S")

def grbl_log(msg, level="info"):
    if msg.startswith(">>") or msg.startswith("<<"):
        return
    socketio.emit("log", {"message": f"[GRBL] {msg}", "level": level, "time": _ts()})

def tester_log(msg, level="info"):
    if msg.startswith(">>") or msg.startswith("<<"):
        return
    socketio.emit("log", {"message": f"[TEST] {msg}", "level": level, "time": _ts()})

grbl.on_log   = grbl_log
tester.on_log = tester_log

# ── Sayfalar ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

# ── REST API ────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    grbl.query_status()
    return jsonify({
        "grbl_connected":        grbl.connected,
        "tester_connected":      tester.connected,
        "camera_connected":      camera.is_open(),
        "yolo_ready":            yolo.is_ready(),
        "grbl_state":            grbl.state,
        "position":              grbl.position,
        "process_running":       process.running,
        "process_paused":        process.paused,
        "current_step":          process.current_step,
        "current_slot":          process.current_slot,
        "placed_components":     process.placed_components,
        "measurements":          process.measurements,
        "errors":                process.errors,
        "last_detection":        process.last_detection,
        "last_placement_verify": process.last_placement_verify,
        "last_test_data":        process.last_test_data,
    })

@app.route("/api/config")
def api_config():
    return jsonify({
        "component_slots": COMPONENT_SLOTS,
        "test_station":    TEST_STATION,
        "pcb_positions":   PCB_POSITIONS,
        "resistor_defs":   RESISTOR_DEFS,
    })

# ── Kamera ──────────────────────────────────────────────────────────

@app.route("/api/camera/snapshot")
def cam_snap():
    jpg = camera.get_jpeg()
    return Response(jpg, mimetype="image/jpeg") if jpg else Response(b"", status=503)

@app.route("/api/camera/overlay")
def cam_overlay():
    import cv2
    frame = camera.get_frame()
    if frame is None:
        return Response(b"", status=503)
    if yolo.is_ready():
        overlay, _ = yolo.detect_and_draw(frame)
        ok, buf = cv2.imencode(".jpg", overlay)
    else:
        ok, buf = cv2.imencode(".jpg", frame)
    return Response(buf.tobytes(), mimetype="image/jpeg") if ok else Response(b"", status=503)

@app.route("/api/camera/stream")
def cam_stream():
    import cv2
    def gen():
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            if yolo.is_ready():
                overlay, _ = yolo.detect_and_draw(frame)
                ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 70])
            else:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(0.066)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/vision/detect")
def vision_detect():
    frame = camera.get_frame()
    if frame is None:
        return jsonify({"error": "no frame"}), 503
    if not yolo.is_ready():
        return jsonify({"error": "yolo not ready"}), 503
    dets = yolo.detect(frame)
    return jsonify({
        "detections": [
            {"class": d.class_name, "score": round(d.score, 4), "box": d.box}
            for d in dets
        ],
        "count": len(dets),
    })

# ── WebSocket ───────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    grbl.query_status()
    socketio.emit("state_update", {
        "running":      process.running,
        "paused":       process.paused,
        "current_step": process.current_step,
        "current_slot": process.current_slot,
        "grbl_state":   grbl.state,
        "placed":       process.placed_components,
        "measurements": process.measurements,
    })
    socketio.emit("position_update", grbl.position)
    socketio.emit("connection_status", {
        "grbl":   grbl.connected,
        "tester": tester.connected,
        "camera": camera.is_open(),
        "yolo":   yolo.is_ready(),
    })

@socketio.on("cmd_connect")
def on_cmd_connect():
    g = grbl.connect()
    t = tester.connect()
    c = camera.open()
    socketio.emit("connection_status", {"grbl": g, "tester": t, "camera": c, "yolo": yolo.is_ready()})
    fails = []
    if not g: fails.append("GRBL")
    if not t: fails.append("Test İst.")
    if not c: fails.append("Kamera")
    if fails:
        socketio.emit("log", {"message": f"❌ Bağlantı hatası: {', '.join(fails)}", "level": "error", "time": _ts()})
    else:
        socketio.emit("log", {"message": "✅ Tüm donanım bağlı", "level": "info", "time": _ts()})

@socketio.on("cmd_disconnect")
def on_cmd_disconnect():
    grbl.disconnect()
    tester.disconnect()
    camera.close()
    socketio.emit("connection_status", {"grbl": False, "tester": False, "camera": False, "yolo": yolo.is_ready()})

@socketio.on("cmd_start")
def on_cmd_start():
    if not grbl.connected or not tester.connected:
        socketio.emit("log", {"message": "❌ Önce donanıma bağlanın!", "level": "error", "time": _ts()})
        return
    process.start()

@socketio.on("cmd_stop")
def on_cmd_stop():
    process.stop()

@socketio.on("cmd_pause")
def on_cmd_pause():
    process.pause()

@socketio.on("cmd_resume")
def on_cmd_resume():
    process.resume()

@socketio.on("cmd_home")
def on_cmd_home():
    if grbl.connected and not process.running:
        grbl.send_command("G0 X0 Y0")
        grbl.query_status()
        socketio.emit("position_update", grbl.position)

@socketio.on("cmd_unlock")
def on_cmd_unlock():
    if grbl.connected:
        grbl.unlock()

@socketio.on("cmd_reset")
def on_cmd_reset():
    if grbl.connected:
        grbl.soft_reset()
        socketio.emit("state_update", {
            "running": False, "paused": False, "current_step": "", "current_slot": 0,
            "grbl_state": grbl.state, "placed": {}, "measurements": {},
        })

@socketio.on("cmd_gcode")
def on_cmd_gcode(data):
    if grbl.connected and not process.running:
        cmd = data.get("command", "").strip()
        if cmd:
            grbl.send_command(cmd)
            grbl.query_status()
            socketio.emit("position_update", grbl.position)

# ── Background Tasks ─────────────────────────────────────────────────

def status_updater():
    while True:
        if grbl.connected:
            grbl.query_status()
            socketio.emit("position_update", grbl.position)
        socketio.sleep(0.5)


def vision_updater():
    """
    Kamera açıksa 0.5s'de bir tespit yapar.

    Hata hesabı mantığı:
      - Tespit edilen bbox merkezi hangi target box içinde?
      - İçindeyse → OK, içinde değilse → FAIL
      - Hata % = target merkeze olan mesafeye göre (0=mükemmel, 100=çok uzak)
      - IoU = target box ile tespit box örtüşme oranı
    """
    while True:
        try:
            if camera.is_open() and yolo.is_ready():
                frame = camera.get_frame()
                if frame is not None:
                    target_areas, pad_names = _build_pixel_targets()

                    # ── Tespit ──────────────────────────────────────
                    if detector is not None:
                        inp     = detector.preprocess(frame)
                        outputs = detector.session.run(None, {detector.input_name: inp})
                        boxes, scores_list, class_ids = detector.postprocess(outputs)
                        det_boxes = boxes
                        det_scores = scores_list
                        det_names = [_CLS_NAMES.get(c, f"cls{c}") for c in class_ids]
                    else:
                        dets = yolo.detect(frame)
                        det_boxes  = [d.box for d in dets]
                        det_scores = [d.score for d in dets]
                        det_names  = [d.class_name for d in dets]

                    if det_boxes:
                        # ── vision_detection emit ────────────────────
                        socketio.emit("vision_detection", {
                            "class":            det_names[0],
                            "score":            round(det_scores[0], 3),
                            "box":              det_boxes[0],
                            "total_detections": len(det_boxes),
                            "time":             _ts(),
                        })

                        # ── Her tespit için en yakın target'ı bul ────
                        best_pad      = "—"
                        best_status   = "FAIL"
                        best_acc      = 0.0
                        best_dist     = None
                        best_iou      = 0.0
                        best_err      = 100.0

                        for det_box in det_boxes:
                            for pad_name, target_box in zip(pad_names, target_areas):
                                inside, dist_px, acc = _check_inside_target(det_box, target_box)
                                iou = yolo.compute_iou(det_box, target_box)

                                if inside or acc > best_acc:
                                    best_pad    = pad_name
                                    best_status = "OK" if inside else "FAIL"
                                    best_acc    = acc
                                    best_dist   = dist_px
                                    best_iou    = round(iou, 4)
                                    best_err    = round(100 - acc, 2)

                        socketio.emit("placement_verify", {
                            "pad":         best_pad,
                            "status":      best_status,
                            "accuracy":    best_acc,
                            "distance_px": best_dist,
                            "iou":         best_iou,
                            "error_pct":   best_err,
                        })

        except Exception as e:
            logger.debug(f"Vision updater error: {e}")
        socketio.sleep(0.5)


if __name__ == "__main__":
    socketio.start_background_task(status_updater)
    socketio.start_background_task(vision_updater)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
