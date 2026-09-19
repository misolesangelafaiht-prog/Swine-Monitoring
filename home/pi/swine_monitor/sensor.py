import numpy as np
import random
import time

try:
    import board
    import busio
    import adafruit_mlx90640
    SIMULATION_MODE = False
    print("[sensor] Real MLX90640 detected!")
except ImportError:
    SIMULATION_MODE = True
    print("[sensor] Simulation mode active")

def setup_sensor():
    if SIMULATION_MODE:
        return None
    import threading
    result = {"mlx": None, "error": None}

    def _init():
        try:
            i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
            mlx = adafruit_mlx90640.MLX90640(i2c)
            mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
            result["mlx"] = mlx
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_init, daemon=True)
    t.start()
    t.join(timeout=10)  # give it 10s max

    if t.is_alive():
        print("[sensor] MLX90640 init timed out (hung) — falling back to simulation")
        return None
    if result["error"]:
        print("[sensor] Error: " + str(result["error"]))
        return None

    print("[sensor] MLX90640 ready!")
    return result["mlx"]

def read_frame(mlx):
    if SIMULATION_MODE or mlx is None:
        return _simulate_frame()
    try:
        frame_flat = [0] * 768
        mlx.getFrame(frame_flat)
        return np.array(frame_flat).reshape(24, 32)
    except Exception as e:
        print("[sensor] Read error: " + str(e))
        return _simulate_frame()

def _simulate_frame():
    frame = []
    for r in range(24):
        row = []
        for c in range(32):
            row.append(25.0 + random.uniform(0, 3))
        frame.append(row)
    for r in range(4, 10):
        for c in range(2, 9):
            frame[r][c] = 36.0 + random.uniform(0, 2)
    for r in range(4, 10):
        for c in range(12, 19):
            frame[r][c] = 36.0 + random.uniform(0, 2)
    if random.random() < 0.3:
        for r in range(4, 10):
            for c in range(12, 19):
                frame[r][c] = 40.5 + random.uniform(0, 1.5)
    return np.array(frame)

def get_temp_stats(frame):
    flat = frame.flatten()
    max_temp = round(float(np.max(flat)), 2)
    min_temp = round(float(np.min(flat)), 2)
    avg_temp = round(float(np.mean(flat)), 2)
    hot_idx = np.unravel_index(np.argmax(frame), frame.shape)
    hot_row = int(hot_idx[0])
    hot_col = int(hot_idx[1])
    if hot_row < 8:
        zone_row = "Top"
    elif hot_row < 16:
        zone_row = "Middle"
    else:
        zone_row = "Bottom"
    if hot_col < 11:
        zone_col = "Left"
    elif hot_col < 21:
        zone_col = "Center"
    else:
        zone_col = "Right"
    return {
        "max_temp": max_temp,
        "min_temp": min_temp,
        "avg_temp": avg_temp,
        "hot_spot_row": hot_row,
        "hot_spot_col": hot_col,
        "hot_zone": zone_row + "-" + zone_col,
        "frame": frame.tolist()
    }

def detect_pig_presence(frame):
    import numpy as np
    arr = np.array(frame)
    # Pig body temperature is warmer than background
    # Background room temp is usually below 33C
    # Pig body surface is usually above 35C
    warm_pixels = np.sum(arr >= 35.0)
    total_pixels = arr.size
    warm_ratio = warm_pixels / total_pixels

    if warm_ratio >= 0.08:
        pig_status = "PIG_DETECTED"
        confidence = round(warm_ratio * 100, 1)
    elif warm_ratio >= 0.03:
        pig_status = "PIG_POSSIBLE"
        confidence = round(warm_ratio * 100, 1)
    else:
        pig_status = "NO_PIG_DETECTED"
        confidence = round(warm_ratio * 100, 1)

    return pig_status, confidence


def detect_activity_state(activity_score, max_temp, nh3_ppm):
    # Distinguish between sleeping and sick
    # Based on: Gonzalez-Sanchez et al. [25]
    # Normal sleeping pig has low activity
    # but normal temperature and ammonia

    if activity_score >= 0.6:
        return "ACTIVE"
    elif activity_score >= 0.25:
        # Low activity — check if sleeping or sick
        if max_temp <= 40.0 and nh3_ppm <= 25:
            return "SLEEPING"
        else:
            return "LETHARGIC"
    else:
        # Very low activity
        if max_temp <= 39.5 and nh3_ppm <= 20:
            return "DEEP_SLEEP"
        else:
            return "LETHARGIC"

def get_status_rules(max_temp):
    if max_temp >= 40.5:
        return "FEVER"
    elif max_temp >= 40.0:
        return "ELEVATED"
    return "NORMAL"
