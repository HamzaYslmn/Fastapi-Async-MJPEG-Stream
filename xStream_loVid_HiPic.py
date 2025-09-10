from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import asyncio
import cv2
import threading
import io

try:
    from picamera2 import Picamera2 #type: ignore
    from picamera2.encoders import MJPEGEncoder, Quality #type: ignore
    from picamera2.outputs import FileOutput #type: ignore
    USE_PICAMERA = True
    print("Using Picamera2")
except ImportError:
    USE_PICAMERA = False
    print("Using OpenCV.")

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
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            broadcast.write(buffer.tobytes())

broadcast = LiveBroadcast()

if USE_PICAMERA:
    picam2 = Picamera2()
    sensor_res = picam2.sensor_resolution
    print(f"Camera sensor resolution: {sensor_res}")
    highres_stream = {"size": sensor_res, "format": "RGB888"}
    midres_stream = {"size": (2304, 1296), "format": "RGB888"}
    lowres_stream = {"size": (1536 , 864), "format": "RGB888"}
    video_config = picam2.create_video_configuration(
        main=highres_stream,
        lores=midres_stream,
        encode="lores",
        controls={"AfMode": 2, "FrameRate": 61}
    )
    picam2.configure(video_config)

def start_camera():
    if USE_PICAMERA:
        picam2.start_recording(MJPEGEncoder(), FileOutput(broadcast), quality=Quality.MEDIUM, name="lores")
    else:
        threading.Thread(target=cv2_capture_thread, daemon=True).start()

async def stream_generator():
    last_frame = None
    while True:
        frame = await asyncio.to_thread(broadcast.get_frame)
        if frame and frame != last_frame:
            last_frame = frame
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        await asyncio.sleep(1 / 60)  # 60 fps

# ───── FastAPI router ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(router: APIRouter):
    try:
        start_camera()
        yield
    except asyncio.CancelledError:
        if USE_PICAMERA:
            picam2.stop_recording()
    except Exception as e:
        print(f"Camera error: {e}")

router = APIRouter(prefix="/camera", tags=["camera"], lifespan=lifespan)

@router.get("/video") #TODO: Implement low,mid,high quality settings
async def video_stream():
    return StreamingResponse(
        stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"}
    )

@router.get("/snap")
async def snapshot():
    if USE_PICAMERA:
        request = await asyncio.to_thread(picam2.capture_request)
        frame = request.make_array("main")
        request.release()
        _, buffer = await asyncio.to_thread(cv2.imencode, '.jpg', frame)
        return Response(buffer.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    else:
        frame_data = await asyncio.to_thread(broadcast.get_frame)
        if frame_data:
            return Response(frame_data, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        return Response(status_code=503)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(router, host="0.0.0.0", port=8000, log_level="info")
