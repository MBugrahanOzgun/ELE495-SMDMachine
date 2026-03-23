"""
File Name       : yolo_runtime.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
YOLO ONNX inference runtime.
Kameradan direnç/diyot tespiti, overlay çizimi, IoU ve hata oranı.
Target box'lar (R1/R2/D1/D2 pad alanları) overlay'e çizilir.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import List, Dict
import cv2
import numpy as np
import logging

logger = logging.getLogger("yolo")

try:
    import onnxruntime as ort
except ImportError:
    ort = None


@dataclass
class Detection:
    box: List[int]
    score: float
    class_id: int
    class_name: str = ""


class YoloRuntime:
    CLASS_NAMES = {0: "resistor", 1: "diode"}

    # PAD piksel koordinatları — placement_verify.py ile aynı değerler
    PAD_PIXEL_CENTER = {
        "R1": (200, 180),
        "R2": (200, 300),
        "D1": (440, 180),
        "D2": (440, 300),
    }
    PAD_BOX_HALF = 30  # her pad için ±30px hedef kutusu

    def __init__(self, model_path, imgsz=640, conf_thres=0.7, iou_thres=0.30,
                 providers=None, class_names=None):
        self.model_path = model_path
        self.imgsz = int(imgsz)
        self.conf_thres = float(conf_thres)
        self.class_names = class_names or self.CLASS_NAMES
        self.session = None
        self.input_name = None

        if ort is None:
            logger.warning("onnxruntime yüklü değil — YOLO devre dışı")
            return
        if not os.path.exists(self.model_path):
            logger.error(f"Model bulunamadı: {self.model_path}")
            return
        try:
            self.session = ort.InferenceSession(
                self.model_path,
                providers=providers or ["CPUExecutionProvider"]
            )
            self.input_name = self.session.get_inputs()[0].name
            logger.info(f"ONNX model yüklendi: {self.model_path}")
        except Exception as e:
            logger.error(f"ONNX model yüklenemedi (YOLO devre dışı): {e}")
            self.session = None
            self.input_name = None

    def is_ready(self):
        return self.session is not None

    def preprocess(self, frame):
        img = cv2.resize(frame, (self.imgsz, self.imgsz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        return np.expand_dims(img, axis=0)

    def postprocess(self, outputs, orig_h, orig_w):
        preds = outputs[0][0].T
        dets = []
        for p in preds:
            cx, cy, w, h = p[:4]
            scores = p[4:]
            cls = int(np.argmax(scores))
            conf = float(scores[cls])
            if conf < self.conf_thres:
                continue
            x1 = max(0, int((cx - w/2) * orig_w / self.imgsz))
            y1 = max(0, int((cy - h/2) * orig_h / self.imgsz))
            x2 = min(orig_w-1, int((cx + w/2) * orig_w / self.imgsz))
            y2 = min(orig_h-1, int((cy + h/2) * orig_h / self.imgsz))
            dets.append(Detection(
                [x1, y1, x2, y2], conf, cls,
                self.class_names.get(cls, f"cls{cls}")
            ))
        dets.sort(key=lambda d: d.score, reverse=True)
        return dets

    def detect(self, frame):
        if not self.is_ready():
            return []
        h, w = frame.shape[:2]
        inp = self.preprocess(frame)
        out = self.session.run(None, {self.input_name: inp})
        return self.postprocess(out, h, w)

    def detect_and_draw(self, frame):
        """
        Tespit kutularını ve PAD hedef alanlarını (Target 0..N) çizer.
        Tespit kutuları: yeşil (resistor) / mor (diode)
        Hedef alanlar  : mavi, "Target N (PadName)" etiketi
        """
        dets = self.detect(frame)
        overlay = frame.copy()

        # ── Hedef pad alanlarını çiz ─────────────────────────────────
        for i, (pad_name, (px, py)) in enumerate(self.PAD_PIXEL_CENTER.items()):
            half = self.PAD_BOX_HALF
            x1, y1 = px - half, py - half
            x2, y2 = px + half, py + half
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 165, 0), 2)  # turuncu
            cv2.putText(
                overlay,
                f"Target {i} ({pad_name})",
                (x1, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (255, 165, 0), 1
            )
            # Pad merkez noktası
            cv2.circle(overlay, (px, py), 3, (255, 165, 0), -1)

        # ── Tespit kutularını çiz ────────────────────────────────────
        for d in dets:
            x1, y1, x2, y2 = d.box
            color = (0, 255, 0) if d.class_name == "resistor" else (255, 0, 255)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                overlay,
                f"{d.class_name} {d.score:.2f}",
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 1
            )

        return overlay, dets

    # ── Geometri yardımcıları ────────────────────────────────────────

    @staticmethod
    def box_center(box):
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    @staticmethod
    def euclidean_distance(p1, p2):
        return float(np.linalg.norm(np.array(p1) - np.array(p2)))

    @staticmethod
    def compute_iou(a, b):
        xa, ya = max(a[0], b[0]), max(a[1], b[1])
        xb, yb = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, xb - xa) * max(0, yb - ya)
        aa = (a[2] - a[0]) * (a[3] - a[1])
        ab = (b[2] - b[0]) * (b[3] - b[1])
        u = aa + ab - inter
        return inter / u if u > 0 else 0.0

    def score_targets(self, target_areas, detected_boxes):
        """
        Her hedef alan için en iyi eşleşen tespit kutusunu bulur.
        Returns: [{"target_box", "matched_box", "iou", "error_pct", "distance_px"}, ...]
        """
        results = []
        for t in target_areas:
            best_iou = 0.0
            best_box = None
            best_dist = float("inf")
            t_center = self.box_center(t)

            for box in detected_boxes:
                iou = self.compute_iou(t, box)
                dist = self.euclidean_distance(t_center, self.box_center(box))
                if iou > best_iou:
                    best_iou = iou
                    best_box = box
                    best_dist = dist

            results.append({
                "target_box":  t,
                "matched_box": best_box,
                "iou":         round(best_iou, 4),
                "error_pct":   round(100 * (1 - best_iou), 2),
                "distance_px": round(best_dist, 2) if best_dist != float("inf") else None,
            })
        return results
