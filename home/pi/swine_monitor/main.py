import time
import random
import threading
import json
import urllib.request
import numpy as np
from datetime import datetime

from sensor import setup_sensor, read_frame, get_temp_stats, get_status_rules
from ammonia import setup_ammonia_sensor, get_ammonia_ppm
from sensor import detect_pig_presence, detect_activity_state
from ml_predict import load_model, predict_status, get_trend
from cloud import send_all
from camera import start_camera, update_thermal
from app import app

history = []
MAX_HISTORY = 100
latest_data = {}


def push_to_dashboard(data):
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:5000/api/update",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def predict_ammonia(nh3_ppm, avg_temp):
    """Simple rule-based ammonia status."""
    if nh3_ppm > 35:
        return "DANGER"
    elif nh3_ppm > 20:
        return "WARNING"
    return "NORMAL"


def predict_activity(activity_score):
    """Derive activity label from warm-pixel ratio (0.0 – 1.0)."""
    if activity_score >= 0.6:
        return "HIGH"
    elif activity_score >= 0.25:
        return "MODERATE"
    return "LOW"


def monitoring_loop():
    global history, latest_data
    print("[main] Setting up sensor...")
    mlx = setup_sensor()
    setup_ammonia_sensor()
    print("[main] Loading ML model...")
    load_model()
    print("[main] Monitoring started!")
    print("[main] Press Ctrl+C to stop")

    while True:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            frame = read_frame(mlx)
            stats = get_temp_stats(frame)
            max_temp = stats["max_temp"]
            avg_temp = stats["avg_temp"]
            min_temp = stats["min_temp"]
            hot_zone = stats["hot_zone"]

            # Detect if pig is present in thermal frame
            pig_status, pig_confidence = detect_pig_presence(frame)

            # Activity score: ratio of warm pixels (0.0 – 1.0)
            # Warm pixels (>=35C) indicate pig movement/presence intensity
            arr = np.array(frame)
            activity_score = round(float(np.sum(arr >= 35.0) / arr.size), 3)

            # Determine activity state — sleeping or lethargic
            activity_state = detect_activity_state(
                activity_score, max_temp, 0  # nh3_ppm not yet read here
            )

            # Only classify health if pig is detected
            if pig_status == "NO_PIG_DETECTED":
                status = "NO_PIG"
                fever_risk = 0.0
                print("[main] No pig detected in thermal frame")
            else:
                status, fever_risk = predict_status(stats, activity_state)

            trend = get_trend()

            # Simulate NH3 reading (replace with real sensor read if available)
            nh3_ppm = get_ammonia_ppm()
            nh3_status = predict_ammonia(nh3_ppm, avg_temp)
            activity = predict_activity(activity_score)

            print(
                "[" + timestamp + "] " +
                "Max:" + str(max_temp) + "C " +
                "Avg:" + str(avg_temp) + "C " +
                "Risk:" + str(fever_risk) + "% " +
                "Status:" + status
            )

            entry = {
                "max_temp"      : max_temp,
                "min_temp"      : min_temp,
                "avg_temp"      : avg_temp,
                "status"        : status,
                "fever_risk"    : fever_risk,
                "trend"         : trend,
                "hot_zone"      : hot_zone,
                "timestamp"     : timestamp,
                "frame"         : stats["frame"],
                "pig_status"    : pig_status,
                "pig_confidence": pig_confidence,
                "activity_state": activity_state,
                "nh3_ppm"       : nh3_ppm,
                "nh3_status"    : nh3_status,
                "activity_score": activity_score,
                "activity"      : activity
            }

            history.append({
                "max_temp" : max_temp,
                "avg_temp" : avg_temp,
                "fever_risk": fever_risk,
                "status"   : status,
                "hot_zone" : hot_zone,
                "timestamp": timestamp
            })
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]

            entry["history"] = history
            latest_data = entry

            update_thermal(stats["frame"], stats)
            push_to_dashboard(entry)
            send_all(
                max_temp=max_temp,
                avg_temp=avg_temp,
                fever_risk=fever_risk,
                status=status,
                trend=trend,
                hot_zone=hot_zone
            )
            time.sleep(1)

        except KeyboardInterrupt:
            print("[main] Stopped.")
            break
        except Exception as e:
            print("[main] Error: " + str(e))
            time.sleep(3)


def start_flask():
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "your-pi-ip"
    print("[dashboard] Open on laptop: http://" + ip + ":5000")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )


if __name__ == "__main__":
    print("=" * 50)
    print("  IoT Swine Flu Early Detection System")
    print("=" * 50)
    camera_thread = threading.Thread(target=start_camera, daemon=True)
    camera_thread.start()
    print("[camera] Starting webcam...")
    time.sleep(2)
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(2)
    monitoring_loop()
