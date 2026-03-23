#!/bin/bash

echo "[ENTRY] Port yonlendirme basliyor..."

# GRBL Portu Ayarla
for dev in /dev/ttyACM*; do
    if [ -e "$dev" ]; then
        ln -sf "$dev" /dev/grbl
        echo "[ENTRY] GRBL cihazı bulundu: $dev -> /dev/grbl"
        break
    fi
done

# Tester Portu Ayarla
for dev in /dev/ttyUSB*; do
    if [ -e "$dev" ]; then
        ln -sf "$dev" /dev/tester
        echo "[ENTRY] Tester cihazı bulundu: $dev -> /dev/tester"
        break
    fi
done

# Cihazlar bulunamasa bile main.py baslatılır
echo "[ENTRY] Uygulama baslatiliyor..."
exec python main.py
