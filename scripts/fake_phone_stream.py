"""Serve a video file as an HTTP MJPEG stream, imitating a phone camera app, for testing the
mobile-camera path without a phone. Usage: python scripts/fake_phone_stream.py [video] [port]
Then add http://127.0.0.1:<port>/video as an HTTP_MJPEG camera in OmniProctor."""
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

video = sys.argv[1] if len(sys.argv) > 1 else "backend/data/media/synthetic_demo.avi"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8081


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path != "/video":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        cap = cv2.VideoCapture(video)
        try:
            while True:
                ok, f = cap.read()
                if not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                jpg = cv2.imencode(".jpg", f)[1].tobytes()
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                time.sleep(1 / 15)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            cap.release()


print(f"Fake phone stream on http://127.0.0.1:{port}/video  (Ctrl+C to stop)")
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
