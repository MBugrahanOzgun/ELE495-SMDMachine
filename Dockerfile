FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 v4l-utils \
    libcap-dev libc6-dev \
    python3-libcamera \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/lib/python3/dist-packages/libcamera \
    /usr/local/lib/python3.13/site-packages/libcamera

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/vision/best.onnx /app/vision/best.onnx
COPY app/ .

EXPOSE 5000
CMD ["python", "main.py"]
