# Fastapi-Async-MJPEG-Stream

A simple **async MJPEG live stream** example with multi-client support. Captures frames from camera sources (OpenCV or Raspberry Pi Picamera2) and streams via FastAPI using **`multipart/x-mixed-replace`**.

---

## Features

* 🚀 Async MJPEG streaming with FastAPI
* 📷 OpenCV & Raspberry Pi **Picamera2** support
* 👥 Multiple clients can connect simultaneously
* 📸 `/video` → live stream, `/snap` → single frame

## Raspberry Pi 5 & CMv3 Example Resolutions/FPS

* **1536×864** → \~100 FPS
* **2304×1296** → \~50 FPS
* **4608×2592** → \~14 FPS

<img width="846" height="390" alt="image" src="https://github.com/user-attachments/assets/183e74ee-6d50-4271-bb4b-5a111ae6ee76" />


## Installation

```bash
pip install fastapi uvicorn opencv-python
```

On Raspberry Pi, install `picamera2` as well.

## Run

```bash
uvicorn xStream_Software:app --host 0.0.0.0 --port 8000
```

Then open in browser:

* `http://localhost:8000/video`
* `http://localhost:8000/snapshot`

## License

AGPL-3.0


