from flask import Flask, jsonify, request, render_template_string, Response
from camera import get_camera_frame, generate_mjpeg
import os

app = Flask(__name__)

latest = {
    "max_temp": 0.0,
    "min_temp": 0.0,
    "avg_temp": 0.0,
    "status": "Starting...",
    "fever_risk": 0.0,
    "trend": "Collecting data...",
    "hot_zone": "--",
    "timestamp": "--",
    "frame": [],
    "history": []
}

@app.route("/")
def index():
    path = "/home/pi/swine_monitor/index.html"
    with open(path) as f:
        html = f.read()
    return render_template_string(html)

@app.route("/api/data")
def api_data():
    return jsonify(latest)

@app.route("/api/camera")
def api_camera():
    """Legacy single-snapshot endpoint (base64 JSON) — kept for compatibility."""
    frame = get_camera_frame()
    if frame:
        return jsonify({"image": frame, "available": True})
    return jsonify({"image": None, "available": False})

@app.route("/video_feed")
def video_feed():
    """Live MJPEG stream — use this in <img src="/video_feed"> for a real live feed."""
    return Response(
        generate_mjpeg(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route("/api/update", methods=["POST"])
def api_update():
    global latest
    data = request.get_json(force=True)
    if data:
        latest.update(data)
    return jsonify({"ok": True})

if __name__ == "__main__":
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "your-pi-ip"
    print("Dashboard at http://" + ip + ":5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
