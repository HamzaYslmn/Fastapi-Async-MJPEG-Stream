from fastapi import FastAPI
from fastapi.responses import StreamingResponse, Response
import cv2
import threading
import asyncio
import time

app = FastAPI()
class Camera:
    def __init__(self, grab_func):
        self.grab = grab_func
        self._frame = None
        self._lock = threading.Lock()
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._run:
            img = self.grab()
            if img is not None:
                with self._lock:
                    self._frame = img

    def frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._run = False

try:
    from picamera2 import Picamera2  # type: ignore
    import logging
    logging.getLogger("picamera2").setLevel(logging.WARNING)

    def _open_picam(size: tuple[int, int] = (2592, 2592)) -> Camera:
        cam = Picamera2()
        cam.configure(cam.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            controls={"FrameRate": 200, "AfMode": 2},
        ))
        cam.start()

        def grab() -> "cv2.Mat":
            rgb = cam.capture_array("main")
            return rgb

        return Camera(grab)

    camera = _open_picam()

except ImportError:
    def _open_cv_cam(cam_src=0) -> Camera:
        cap = cv2.VideoCapture(cam_src, cv2.CAP_DSHOW if isinstance(cam_src, int) else 0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
        max_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        max_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        def grab() -> "cv2.Mat":
            ret, frame = cap.read()
            if ret:
                min_dim = min(max_width, max_height)
                h, w = frame.shape[:2]
                x_start = (w - min_dim) // 2
                y_start = (h - min_dim) // 2
                frame = frame[slice(y_start, y_start+min_dim), slice(x_start, x_start+min_dim)]
            return frame if ret else None

        return Camera(grab)

    camera = _open_cv_cam()

def get_camera_fps(grab_func):
    for _ in range(10):
        frame = grab_func()
        if frame is None:
            break
    frame_count = 0
    start_time = time.time()
    while frame_count < 60:
        frame = grab_func()
        if frame is None:
            break
        frame_count += 1
    end_time = time.time()
    fps = frame_count / (end_time - start_time)
    print(f"Camera FPS: {fps:.2f}")
    return fps

fps = get_camera_fps(camera.grab)

async def generate_frames():
    global fps
    next_tick = time.perf_counter()
    while True:
        next_tick += 1 / fps
        await asyncio.sleep(max(next_tick - time.perf_counter(), 0.0))
        frame = camera.frame()
        if frame is not None:
            _, buffer = cv2.imencode(".jpg", frame)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                   buffer.tobytes() + b"\r\n")

@app.get("/video", summary="Live MJPEG camera feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/snapshot", summary="Tek seferlik kamera görüntüsü")
async def snapshot():
    frame = camera.frame()
    if frame is None:
        return Response(status_code=503)
    _, buffer = cv2.imencode(".jpg", frame)
    return Response(buffer.tobytes(), media_type="image/jpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
