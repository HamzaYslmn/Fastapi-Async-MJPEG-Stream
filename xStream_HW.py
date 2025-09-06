from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
import asyncio
import cv2
import threading
import io

try:
    from picamera2 import Picamera2 #type: ignore
    from picamera2.encoders import MJPEGEncoder, Quality #type: ignore
    from picamera2.outputs import FileOutput #type: ignore
    USE_PICAMERA = True
except ImportError:
    USE_PICAMERA = False

app = FastAPI()

class LiveBroadcast(io.BufferedIOBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._frame = None

    def write(self, buf):
        with self._lock:
            self._frame = bytes(buf)
        return len(buf)

    def get_frame(self):
        with self._lock:
            return self._frame

    def update_frame(self, frame):
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.write(buffer.tobytes())

def _open_cv_cam(cam_src=0):
    cap = cv2.VideoCapture(cam_src, cv2.CAP_DSHOW if isinstance(cam_src, int) else 0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap

def cv2_capture_thread():
    cap = _open_cv_cam()
    while True:
        ret, frame = cap.read()
        if ret:
            broadcast.update_frame(frame)

broadcast = LiveBroadcast()

if USE_PICAMERA:
    picam2 = Picamera2()
    picam2.configure(
        picam2.create_video_configuration(
            main={"size": (4608, 2592), "format": "RGB888"}, controls={"AfMode": 2, "FrameRate": 30}
        )
    )
    picam2.start_recording(MJPEGEncoder(), FileOutput(broadcast), quality=Quality.HIGH)
else:
    threading.Thread(target=cv2_capture_thread, daemon=True).start()

async def stream_generator():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    last_frame = None
    while True:
        frame = await asyncio.to_thread(broadcast.get_frame)
        if frame and frame != last_frame:
            last_frame = frame
            yield boundary + frame + b"\r\n"
        await asyncio.sleep(0.01)

@app.get("/video")
async def video_stream():
    return StreamingResponse(
        stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/snap")
async def snapshot():
    if USE_PICAMERA:
        frame = await asyncio.to_thread(picam2.capture_array)
        _, buffer = cv2.imencode('.jpg', frame)
        return Response(buffer.tobytes(), media_type="image/jpeg")
    else:
        cap = _open_cv_cam()
        ret, frame = cap.read()
        cap.release()
        if ret:
            _, buffer = cv2.imencode('.jpg', frame)
            return Response(buffer.tobytes(), media_type="image/jpeg")
        return Response(status_code=503)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
