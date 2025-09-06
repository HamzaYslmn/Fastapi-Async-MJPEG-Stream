from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import cv2
import threading
import asyncio

app = FastAPI()
latest_frame = None

def camera_worker():
    global latest_frame
    cap = cv2.VideoCapture(0)
    while True:
        success, frame = cap.read()
        if not success:
            continue
        _, buffer = cv2.imencode(".jpg", frame)
        latest_frame = buffer.tobytes()

threading.Thread(target=camera_worker, daemon=True).start()

async def generate_frames():
    global latest_frame
    while True:
        await asyncio.sleep(0.03)  # ~30 FPS
        if latest_frame:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + latest_frame + b"\r\n")

@app.get("/video")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
