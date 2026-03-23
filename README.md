Bu proje, CNC tabanlı bir **Pick & Place (Dizgi) Kontrol Sistemi** için geliştirilmiş bir yazılım arayüzü ve kontrol mekanizmasıdır. Sistem; Arduino tabanlı bir GRBL kontrolcü, bir test istasyonu, kamera modülü ve YOLO tabanlı bir görüntü işleme modelini bir araya getirerek elektronik bileşenlerin (direnç, diyot vb.) otomatik olarak test edilmesini ve PCB üzerine yerleştirilmesini sağlar.

Aşağıda projenin detaylarını içeren örnek bir **README.md** dosyası yer almaktadır:

---

# CNC Pick & Place Kontrol Sistemi

Bu proje, masaüstü bir CNC makinesini otomatik bir SMD dizgi makinesine dönüştüren tam kapsamlı bir kontrol yazılımıdır. Sistem, bileşenleri belirlenen slotlardan alır, test istasyonunda elektriksel karakteristiklerini doğrular (direnç değeri, diyot yönü vb.) ve ardından görüntü işleme desteğiyle PCB üzerindeki doğru koordinatlara yerleştirir.

## 🚀 Özellikler

* **GRBL Entegrasyonu:** CNC hareketleri için standart GRBL protokolü üzerinden haberleşme.
* **Otomatik Test Süreci:** Bileşenler yerleştirilmeden önce test istasyonunda ölçülür ve tanımlanır.
* **Görüntü İşleme (YOLO):** ONNX tabanlı YOLO modeli ile bileşen tespiti ve yerleştirme doğruluğu kontrolü (IoU ve piksel bazlı hata hesabı).
* **Diyot Yönü Düzeltme:** Test istasyonunda diyotun ters olduğu tespit edilirse, makine diyotu otomatik olarak döndürür.
* **Web Arayüzü:** Flask ve SocketIO tabanlı gerçek zamanlı izleme ve kontrol paneli.
* **Docker Desteği:** Tüm bağımlılıkların kolayca kurulabilmesi için Dockerize edilmiş yapı.

## 🛠 Donanım ve Yazılım Gereksinimleri

* **Kontrolcü:** Arduino Uno (GRBL yüklü).
* **Test İstasyonu:** Seri port üzerinden veri gönderen özel test devresi.
* **Kamera:** Raspberry Pi kamera modülü veya standart USB WebCam.
* **Yazılım:** Python 3.13+, Docker ve Docker Compose.

## 📁 Proje Yapısı

* `app/main.py`: Flask sunucusu ve ana WebSocket olayları.
* `app/process.py`: Pick & Place iş akışının (algoritmanın) yönetildiği ana dosya.
* `app/grbl.py`: CNC hareket komutlarını yöneten sürücü.
* `app/vision/`: YOLO runtime ve görüntü işleme algoritmaları.
* `app/config.py`: Koordinatların, hız ayarlarının ve port tanımlarının bulunduğu yapılandırma dosyası.

## ⚙️ Kurulum ve Çalıştırma

### Docker ile Çalıştırma (Önerilen)

Sistemi tüm bağımlılıklarıyla birlikte ayağa kaldırmak için aşağıdaki komutu projenin ana dizininde çalıştırın:

```bash
docker-compose up --build
```

Bu komut, gerekli Python kütüphanelerini (Flask, OpenCV, ONNX Runtime vb.) kuracak ve web sunucusunu `http://localhost:5000` adresinden yayına alacaktır.

### Manuel Kurulum

1. Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
2. `app/config.py` dosyasındaki seri port yollarını (`GRBL_PORT`, `TESTER_PORT`) kendi sisteminize göre güncelleyin.
3. Uygulamayı başlatın:
   ```bash
   python app/main.py
   ```

## 🕹 Kullanım

1.  Web arayüzüne giriş yapın.
2.  **"Bağlan"** butonu ile GRBL, Test İstasyonu ve Kamera bağlantılarını aktifleştirin.
3.  **"Başlat"** butonuna basarak 8 slotluk otomatik dizgi sürecini başlatın.
4.  Süreci arayüzdeki canlı kamera yayını ve log panelinden takip edebilirsiniz.

## 👥 Yazarlar

* Mustafa Buğrahan Özgün
* Mert Şenel
* Eda İnan
* Ayşenur Kurt

--- 

*Bu proje ELE495 dersi kapsamında geliştirilmiştir.*
