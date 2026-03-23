"""
File Name       : config.py
Author          : Mustafa Buğrahan Özgün, Mert Şenel
Project         : CNC Pick & Place Kontrol Sistemi
Created Date    : 2026-03-15

Description:
Tüm koordinatlar, seri port ayarları, komponent tanımları ve
Z ekseni parametreleri.
"""

# ── Seri Port Ayarları ──────────────────────────────────────────────
# GRBL: Arduino Uno R3 (CDC ACM) → /dev/ttyACM0
GRBL_PORT = "/dev/grbl"
GRBL_BAUD = 115200

# Test İstasyonu: CH340 → /dev/ttyUSB0
TESTER_PORT = "/dev/tester"
TESTER_BAUD = 115200

# ── Z Ekseni Ayarları ───────────────────────────────────────────────
SAFE_Z = 6           # Hareket ederken güvenli yükseklik  → G0 Z15
PICK_Z = 13          # Komponent alma derinliği            → G1 Z-20 F200
PLACE_Z = 13         # Komponent bırakma derinliği         → G1 Z-20 F200
TEST_Z =20.5          # Test istasyonu derinliği             → G1 Z-20 F200
Z_FEED = 200          # Aşağı iniş hızı (mm/dk)

# ── Hız Ayarları ────────────────────────────────────────────────────
TRAVEL_FEED = 1000
PROBE_FEED = 60

# ── Başlatma Sekansı ────────────────────────────────────────────────
INIT_SEQUENCE = [
    "G92 X0 Y0",
    "G0 X10 Y10",
    "G38.2 Z-60 F60",
    "G92 Z0",
]

# ── Komponent Alma Pozisyonları (8 slot) ────────────────────────────
COMPONENT_SLOTS = [
    {"index": 1, "x": 14.0, "y": 61.0},
    {"index": 2, "x": 14.0, "y": 86},
    {"index": 3, "x": 14.0, "y": 112.5},
    {"index": 4, "x": 14.0, "y": 137.5},
    {"index": 5, "x": 14.0, "y": 162.5},
    {"index": 6, "x": 14.0, "y": 187.5},
    {"index": 7, "x": 14.0, "y": 213},
    {"index": 8, "x": 14.0, "y": 238},
]

# ── Test İstasyonu Konumu ───────────────────────────────────────────
TEST_STATION = {"x": 266.2, "y": 99.26}

# ── Komponent Tanımları (Direnç değerleri Ohm cinsinden) ────────────
RESISTOR_DEFS = {
    "R1": {"nominal": 10000,  "min": 9000,   "max": 11000,  "label": "10KΩ"},
    "R2": {"nominal": 33000,  "min": 29700,  "max": 36300,  "label": "33KΩ"},
    "R3": {"nominal": 100000, "min": 90000,  "max": 110000, "label": "100KΩ"},
    "R4": {"nominal": 4700,   "min": 4230,   "max": 5170,   "label": "4.7KΩ"},
    "R5": {"nominal": 1000,   "min": 900,    "max": 1100,   "label": "1KΩ"},
    "R6": {"nominal": 125,    "min": 50,     "max": 200,    "label": "50-200Ω"},
}

# ── PCB Yerleştirme Koordinatları ───────────────────────────────────
# Sadece PCB üzerinde yeri olan komponentler:
PCB_POSITIONS = {
    "R2": {"x": 495, "y": 107.26},
    "R1": {"x": 495, "y": 137.25},
    "D2": {"x": 539.0,   "y": 107.26},
    "D1": {"x": 539.0,   "y": 137.25},
}

# ── Kamera / Görüntü İşleme ────────────────────────────────────────
CAMERA_DEVICE = 0
CAMERA_DEMO_MODE = False
ONNX_MODEL_PATH = "/app/vision/best.onnx"
ONNX_CONF_THRESHOLD = 0.7
ONNX_IMG_SIZE = 640

# ── Zamanlama ───────────────────────────────────────────────────────
VACUUM_SETTLE_TIME = 0.5
TEST_DWELL_SECONDS = 3
SERIAL_TIMEOUT = 10
GRBL_OK_TIMEOUT = 30
