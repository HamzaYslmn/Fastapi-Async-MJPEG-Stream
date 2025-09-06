from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import cv2
import threading
import asyncio
import time

app = FastAPI()
latest_frame = None
fps = 15

def get_camera_fps(cap):
    for _ in range(10):
        ret, frame = cap.read()
        if not ret:
            break
    frame_count = 0
    start_time = time.time()
    while frame_count < 60:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
    end_time = time.time()
    fps = round(frame_count / (end_time - start_time))
    return fps

def camera_worker(src=0):
    global latest_frame, fps
    cap = cv2.VideoCapture(src, cv2.CAP_DSHOW if isinstance(src, int) else 0)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    fps = get_camera_fps(cap)
    print(f"Camera FPS: {fps}")
    while True:
        success, frame = cap.read()
        if not success:
            continue
        _, buffer = cv2.imencode(".jpg", frame)
        latest_frame = buffer.tobytes()

threading.Thread(target=camera_worker, daemon=True).start()

async def generate_frames():
    global latest_frame, fps
    while True:
        await asyncio.sleep(1 / fps)
        if latest_frame:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + latest_frame + b"\r\n")

@app.get("/video")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
