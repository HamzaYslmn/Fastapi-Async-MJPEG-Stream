from fastapi import FastAPI, Response, Query
from fastapi.responses import StreamingResponse
import asyncio
import io
import threading
import cv2

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
        self._lock = threading.RLock()
        self._frame = None
        self._clients = set()
        self._events = {}

    def write(self, buf):
        data = bytes(buf)
        with self._lock:
            self._frame = data
            # Wake all waiting clients
            for client_id in list(self._clients):
                if client_id in self._events:
                    self._events[client_id].set()
        return len(buf)

    def add_client(self):
        client_id = id(threading.current_thread())
        with self._lock:
            self._clients.add(client_id)
            self._events[client_id] = threading.Event()
        return client_id

    def remove_client(self, client_id):
        with self._lock:
            self._clients.discard(client_id)
            self._events.pop(client_id, None)

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

# Camera setup
broadcast = LiveBroadcast()

if USE_PICAMERA:
    picam2 = Picamera2()
    picam2.configure(
        picam2.create_video_configuration(
            #main= {"size": (1536 , 864), "format": "RGB888"}, controls={"AfMode": 2, "FrameRate": 50}
            #main= {"size": (2304, 1296), "format": "RGB888"}, controls={"AfMode": 2, "FrameRate": 50}
            main={"size": (4608, 2592), "format": "RGB888"}, controls={"AfMode": 2, "FrameRate": 30}
        )
    )
    picam2.start_recording(MJPEGEncoder(), FileOutput(broadcast), quality=Quality.HIGH)
else:
    threading.Thread(target=cv2_capture_thread, daemon=True).start()

async def stream_generator():
    client_id = broadcast.add_client()
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    last_frame = None
    try:
        while True:
            frame = await asyncio.to_thread(broadcast.get_frame)
            if frame and frame != last_frame:
                last_frame = frame
                yield boundary + frame + b"\r\n"
            else:
                await asyncio.sleep(0.01)
    except Exception:
        pass
    finally:
        broadcast.remove_client(client_id)

@app.get("/video") #TODO: Implement low,mid,high quality settings
async def video_stream():
    return StreamingResponse(
        stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/snap")
async def snapshot():
    if USE_PICAMERA:
        # Capture a full-res frame directly from Picamera2
        frame = await asyncio.to_thread(picam2.capture_array)
        _, buffer = cv2.imencode('.jpg', frame)
        return Response(buffer.tobytes(), media_type="image/jpeg")
    else:
        # For OpenCV, try to get a fresh frame at max resolution
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
