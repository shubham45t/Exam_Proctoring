# Using a phone as the camera source

OmniProctor only needs a **URL that serves video**. The phone does no AI processing. Verified in this repo: the HTTP/MJPEG adapter against a local stand-in server. **Not yet verified: any specific phone app.** Apps differ, so use the URL *your app displays*; do not guess paths.

## Recommended approach: an app that serves MJPEG over HTTP
Choose an "IP webcam"-style app (e.g. Android "IP Webcam"; iOS equivalents exist). Use only apps you trust and have reviewed. In the app:
1. Start the server/stream. The app shows an address like `http://<phone-ip>:<port>`.
2. Find the *video stream* path in the app's help page (commonly something like `/video`, but this varies by app/version).
3. Lower resolution/quality (e.g. 640x480 to 1280x720) for lower latency; ~10-15 fps is enough for development.

## Steps
1. **Same network.** Phone and computer must be on the same Wi-Fi/LAN. Guest Wi-Fi and many campus networks isolate clients; if so use a phone hotspot or a personal router.
2. **Find the computer's LAN IP** (only needed if the phone must reach the computer; here the computer connects *to the phone*). Phone IP is shown by the app, or in Wi-Fi settings.
3. **Test independently first:** open the stream URL in VLC (Media -> Open Network Stream) or a desktop browser on the computer. If that fails, OmniProctor will fail too.
4. **Add in OmniProctor:** Cameras -> source type `Phone / HTTP (MJPEG)` -> paste the URL -> *Add camera* -> **Test connection**. A successful test reports resolution and measured fps. If the app needs a login, use `http://user:pass@host:port/path`; credentials are stored server-side and never displayed back.
5. **Start.** The camera badge should become CONNECTED. If the phone sleeps or Wi-Fi drops it becomes FAILED/STALE and reconnects automatically with exponential backoff (1 s up to 30 s by default).

## RTSP
If your app or CCTV exposes RTSP, choose `RTSP` and use its `rtsp://...` URL. This adapter is implemented (TCP transport) but **untested against real hardware**.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Test says OPEN_FAILED | Wrong URL/path, app not running or backgrounded, different network, firewall |
| NO_FRAMES | Wrong path (page loads but isn't a video stream), or authentication rejected |
| Works in browser, not in OmniProctor | Stream is not MJPEG/RTSP (e.g. WebRTC/HLS-only apps are unsupported) |
| High latency / low fps | Lower the phone resolution/quality; check Wi-Fi signal |
| DEGRADED (DARK/BLURRY) | Genuinely dark/blurred image, or thresholds need calibration |
| FROZEN | Frames arrive but the image never changes (camera hung or paused) |

## No phone available?
`python scripts/fake_phone_stream.py <video> 8081` serves a video as an MJPEG stream at `http://127.0.0.1:8081/video`.
