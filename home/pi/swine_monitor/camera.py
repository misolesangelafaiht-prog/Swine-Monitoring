import cv2
import base64
import threading
import time
import numpy as np
import os
from picamera2 import Picamera2

camera_frame = None          # latest frame as raw JPEG bytes (for MJPEG stream)
camera_frame_b64 = None      # latest frame as base64 (for legacy /api/camera)
camera_lock = threading.Lock()
camera_running = False
current_thermal = None
thermal_lock = threading.Lock()

# ── Alignment calibration ──────────────────────────────────
CALIB = {
    "offset_x": 0.0,
    "offset_y": 0.0,
    "scale_x": 1.0,
    "scale_y": 1.0,
}

DEBUG_CALIBRATION = os.environ.get("DEBUG_CALIBRATION", "0") == "1"
OVERLAY_MODE = os.environ.get("THERMAL_OVERLAY", "both")
OVERLAY_ALPHA = 0.45
HEATMAP_T_MIN = 24.0
HEATMAP_T_MAX = 42.0

_cached_overlay = None
_cached_overlay_key = None


def update_thermal(frame, stats):
    global current_thermal
    with thermal_lock:
        current_thermal = {
            "frame": frame,
            "stats": stats
        }


def find_hot_zones(frame, threshold=36.0):
    zones = []
    if frame is None:
        return zones
    arr = np.array(frame)
    rows, cols = arr.shape
    visited = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if arr[r][c] >= threshold and not visited[r][c]:
                zone_temps = []
                cells = []
                stack = [(r, c)]
                while stack:
                    cr, cc = stack.pop()
                    if cr < 0 or cr >= rows:
                        continue
                    if cc < 0 or cc >= cols:
                        continue
                    if visited[cr][cc]:
                        continue
                    if arr[cr][cc] < threshold:
                        continue
                    visited[cr][cc] = True
                    zone_temps.append(arr[cr][cc])
                    cells.append((cr, cc))
                    stack.extend([
                        (cr + 1, cc),
                        (cr - 1, cc),
                        (cr, cc + 1),
                        (cr, cc - 1)
                    ])
                if len(cells) >= 4:
                    min_r = min(x[0] for x in cells)
                    max_r = max(x[0] for x in cells)
                    min_c = min(x[1] for x in cells)
                    max_c = max(x[1] for x in cells)
                    max_temp = round(float(max(zone_temps)), 1)
                    zones.append({
                        "min_row": min_r,
                        "max_row": max_r,
                        "min_col": min_c,
                        "max_col": max_c,
                        "max_temp": max_temp
                    })
    return zones


def _apply_calib(nx, ny):
    cx, cy = 0.5, 0.5
    nx = cx + (nx - cx) * CALIB["scale_x"] + CALIB["offset_x"]
    ny = cy + (ny - cy) * CALIB["scale_y"] + CALIB["offset_y"]
    nx = max(0.0, min(1.0, nx))
    ny = max(0.0, min(1.0, ny))
    return nx, ny


def draw_boxes(cam_frame, thermal_frame, cam_w, cam_h):
    if thermal_frame is None:
        return cam_frame
    try:
        zones = find_hot_zones(thermal_frame, threshold=36.0)
        thermal_rows = 24
        thermal_cols = 32
        for zone in zones:
            nx1, ny1 = _apply_calib(
                zone["min_col"] / thermal_cols,
                zone["min_row"] / thermal_rows
            )
            nx2, ny2 = _apply_calib(
                zone["max_col"] / thermal_cols,
                zone["max_row"] / thermal_rows
            )

            x1 = int(nx1 * cam_w)
            y1 = int(ny1 * cam_h)
            x2 = int(nx2 * cam_w)
            y2 = int(ny2 * cam_h)

            temp = zone["max_temp"]
            if temp >= 40.5:
                color = (0, 0, 255)
                label = "FEVER " + str(temp) + "C"
            elif temp >= 40.0:
                color = (0, 165, 255)
                label = "HIGH " + str(temp) + "C"
            else:
                color = (0, 255, 0)
                label = str(temp) + "C"
            cv2.rectangle(cam_frame, (x1, y1), (x2, y2), color, 2)
            label_y = y1 - 6
            if label_y < 20:
                label_y = y2 + 16
            box_w = len(label) * 9
            cv2.rectangle(cam_frame, (x1, y1 - 22), (x1 + box_w, y1), color, -1)
            cv2.putText(
                cam_frame, label,
                (x1 + 2, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1
            )
    except Exception as e:
        print("[camera] Box error: " + str(e))
    return cam_frame


def draw_calibration_grid(cam_frame, cam_w, cam_h):
    try:
        thermal_rows, thermal_cols = 24, 32
        for r in range(0, thermal_rows + 1, 4):
            _, ny = _apply_calib(0.5, r / thermal_rows)
            y = int(ny * cam_h)
            cv2.line(cam_frame, (0, y), (cam_w, y), (0, 255, 255), 1)
        for c in range(0, thermal_cols + 1, 4):
            nx, _ = _apply_calib(c / thermal_cols, 0.5)
            x = int(nx * cam_w)
            cv2.line(cam_frame, (x, 0), (x, cam_h), (0, 255, 255), 1)
        cv2.putText(
            cam_frame, "CALIBRATION MODE",
            (10, cam_h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5, (0, 255, 255), 1
        )
    except Exception as e:
        print("[camera] Calibration grid error: " + str(e))
    return cam_frame


def _build_thermal_overlay_raw(thermal_frame, cam_w, cam_h):
    try:
        arr = np.array(thermal_frame, dtype=np.float32)
        norm = np.clip((arr - HEATMAP_T_MIN) / (HEATMAP_T_MAX - HEATMAP_T_MIN), 0, 1)
        norm_8u = (norm * 255).astype(np.uint8)
        norm_resized = cv2.resize(norm_8u, (cam_w, cam_h), interpolation=cv2.INTER_CUBIC)
        colored = cv2.applyColorMap(norm_resized, cv2.COLORMAP_JET)

        cx, cy = cam_w / 2.0, cam_h / 2.0
        tx = CALIB["offset_x"] * cam_w
        ty = CALIB["offset_y"] * cam_h
        M = np.array([
            [CALIB["scale_x"], 0, cx - cx * CALIB["scale_x"] + tx],
            [0, CALIB["scale_y"], cy - cy * CALIB["scale_y"] + ty]
        ], dtype=np.float32)
        aligned = cv2.warpAffine(colored, M, (cam_w, cam_h), borderValue=(0, 0, 0))
        return aligned
    except Exception as e:
        print("[camera] Overlay build error: " + str(e))
        return None


def build_thermal_overlay(thermal_frame, cam_w, cam_h):
    global _cached_overlay, _cached_overlay_key
    if thermal_frame is None:
        return None
    try:
        key = (cam_w, cam_h, hash(np.array(thermal_frame).tobytes()))
    except Exception:
        key = None

    if key is not None and key == _cached_overlay_key and _cached_overlay is not None:
        return _cached_overlay.copy()

    overlay = _build_thermal_overlay_raw(thermal_frame, cam_w, cam_h)
    if overlay is not None and key is not None:
        _cached_overlay = overlay
        _cached_overlay_key = key
    return overlay


def apply_thermal_overlay(cam_frame, thermal_frame, cam_w, cam_h, alpha=None):
    if alpha is None:
        alpha = OVERLAY_ALPHA
    overlay = build_thermal_overlay(thermal_frame, cam_w, cam_h)
    if overlay is None:
        return cam_frame
    try:
        blended = cv2.addWeighted(overlay, alpha, cam_frame, 1 - alpha, 0)
        return blended
    except Exception as e:
        print("[camera] Overlay blend error: " + str(e))
        return cam_frame


def start_camera():
    global camera_frame, camera_frame_b64, camera_running
    camera_running = True
    print("[camera] Starting Arducam OV5647 (picamera2 mode)...")
    print("[camera] Overlay mode: " + OVERLAY_MODE)
    if DEBUG_CALIBRATION:
        print("[camera] DEBUG_CALIBRATION is ON — grid overlay active")

    picam2 = None
    try:
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
        time.sleep(1)  # let auto-exposure/white-balance settle
        print("[camera] Arducam started OK")
    except Exception as e:
        print("[camera] Failed to start Arducam: " + str(e))
        camera_running = False
        return

    fail_count = 0
    while camera_running:
        try:
            frame = picam2.capture_array()  # returns RGB888 numpy array
            if frame is None:
                fail_count += 1
                print("[camera] Frame capture failed (" + str(fail_count) + ")")
                time.sleep(0.5)
                if fail_count >= 10:
                    print("[camera] Too many failures — restarting camera")
                    try:
                        picam2.stop()
                        time.sleep(1)
                        picam2.start()
                        fail_count = 0
                    except Exception as e2:
                        print("[camera] Restart failed: " + str(e2))
                continue

            fail_count = 0

            # picamera2 gives RGB — convert to BGR for OpenCV drawing/encoding
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            h, w = frame.shape[:2]

            with thermal_lock:
                thermal_data = current_thermal

            if thermal_data is not None:
                t_frame = thermal_data["frame"]
                if OVERLAY_MODE == "heatmap":
                    frame = apply_thermal_overlay(frame, t_frame, w, h)
                elif OVERLAY_MODE == "both":
                    frame = apply_thermal_overlay(frame, t_frame, w, h)
                    frame = draw_boxes(frame, t_frame, w, h)
                else:  # "boxes"
                    frame = draw_boxes(frame, t_frame, w, h)

                if DEBUG_CALIBRATION:
                    frame = draw_calibration_grid(frame, w, h)

            ret2, buffer = cv2.imencode(
                '.jpg', frame,
                [cv2.IMWRITE_JPEG_QUALITY, 70]
            )
            if ret2:
                jpg_bytes = buffer.tobytes()
                with camera_lock:
                    camera_frame = jpg_bytes
                    camera_frame_b64 = base64.b64encode(jpg_bytes).decode('utf-8')

        except Exception as e:
            print("[camera] Error: " + str(e))
            time.sleep(0.5)
            continue

        time.sleep(0.03)  # ~30fps cap, gentle on Pi CPU

    if picam2 is not None:
        try:
            picam2.stop()
        except Exception:
            pass
    print("[camera] Capture loop ended, camera released")


def get_camera_frame():
    """Legacy base64 snapshot — used by /api/camera."""
    for _ in range(30):
        with camera_lock:
            if camera_frame_b64 is not None:
                return camera_frame_b64
        time.sleep(0.5)
    return None


def generate_mjpeg():
    """Generator that yields multipart JPEG frames for streaming."""
    while True:
        with camera_lock:
            frame = camera_frame
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.05)


def stop_camera():
    global camera_running
    camera_running = False
    print("[camera] Stopped")
