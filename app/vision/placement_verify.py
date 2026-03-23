"""
File Name       : placement_verify.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
Yerleştirme doğrulama — bbox merkezi vs. beklenen pad merkezi.
PAD_PIXEL_CENTER: 640x480 kamera görüntüsü için tahmini piksel koordinatları.
Gerçek koordinatlar kalibrasyonla güncellenmelidir.
"""

from __future__ import annotations
import math
from typing import Dict, Tuple

# ── Pad piksel koordinatları (640x480 görüntü için) ──────────────────
# Kamera PCB'nin üzerinde sabit konumdaysa bu değerler kalibrasyon ile
# güncellenmeli. Şimdilik makul tahmin değerleri kullanılmıştır.
PAD_PIXEL_CENTER: Dict[str, Tuple[int, int]] = {
    "R1": (236, 296),   # Sol üst bölge
    "R2": (236, 420),   # Sol alt bölge
    "D1": (476, 276),   # Sağ üst bölge
    "D2": (476, 420),   # Sağ alt bölge
}


def bbox_center(box: list) -> Tuple[int, int]:
    x1, y1, x2, y2 = box
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def verify_placement(pad_label: str, det_box: list, tolerance_px: int = 45) -> dict:
    """
    Tespit edilen bbox merkezini beklenen pad merkezi ile karşılaştırır.

    Args:
        pad_label    : Pad ismi (R1, R2, D1, D2)
        det_box      : [x1, y1, x2, y2] tespit kutusu
        tolerance_px : Kabul edilebilir max piksel sapması (varsayılan 30px)

    Returns:
        dict: pad, status, accuracy, distance_px, center, target, tolerance_px
    """
    pad_label = pad_label.upper()
    target    = PAD_PIXEL_CENTER.get(pad_label)
    cx, cy    = bbox_center(det_box)

    if target is None:
        return {
            "pad":          pad_label,
            "status":       "UNKNOWN_PAD",
            "accuracy":     0.0,
            "distance_px":  None,
            "center":       {"x": cx, "y": cy},
            "target":       None,
            "tolerance_px": tolerance_px,
        }

    tx, ty = target
    dist   = math.sqrt((cx - tx) ** 2 + (cy - ty) ** 2)
    acc    = max(0.0, 100.0 * (1.0 - (dist / (2.0 * tolerance_px))))

    return {
        "pad":          pad_label,
        "status":       "OK" if dist <= tolerance_px else "FAIL",
        "accuracy":     round(acc, 2),
        "distance_px":  round(dist, 2),
        "center":       {"x": cx, "y": cy},
        "target":       {"x": tx, "y": ty},
        "tolerance_px": tolerance_px,
    }
