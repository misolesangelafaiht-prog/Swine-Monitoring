import pickle
import numpy as np
import os
import random
from collections import deque

model_temp = None
model_nh3 = None
model_activity = None
temp_history = deque(maxlen=5)
prev_zone = None
zone_changes = 0


def load_model():
    global model_temp, model_nh3, model_activity
    path_temp = "/home/pi/swine_monitor/pig_model.pkl"
    path_nh3  = "/home/pi/swine_monitor/pig_model_nh3.pkl"
    path_act  = "/home/pi/swine_monitor/pig_model_activity.pkl"

    if os.path.exists(path_temp):
        with open(path_temp, "rb") as f:
            model_temp = pickle.load(f)
        print("[ML] Temperature model loaded!")
    else:
        print("[ML] No temperature model found — using rules")

    if os.path.exists(path_nh3):
        with open(path_nh3, "rb") as f:
            model_nh3 = pickle.load(f)
        print("[ML] Ammonia model loaded!")
    else:
        print("[ML] No ammonia model found — using rules")

    if os.path.exists(path_act):
        with open(path_act, "rb") as f:
            model_activity = pickle.load(f)
        print("[ML] Activity model loaded!")
    else:
        print("[ML] No activity model found — using rules")

    return model_temp is not None


def predict_status(stats, activity_state="ACTIVE"):
    # FIX: was incorrectly referencing bare 'model' — now uses 'model_temp'
    global model_temp
    max_temp = stats["max_temp"]
    avg_temp = stats["avg_temp"]

    # Sleeping pig: classify as HEALTHY regardless of temp
    # Based on Gonzalez-Sanchez et al. [25]
    if activity_state in ["SLEEPING", "DEEP_SLEEP"]:
        print("[ML] Pig is sleeping — classifying as HEALTHY")
        return "HEALTHY", 2.0

    if model_temp is None:
        # Rule-based fallback
        if max_temp >= 40.5:
            return "FEVER", 95.0
        elif max_temp >= 40.0:
            return "ELEVATED", 60.0
        return "NORMAL", 5.0

    temp_history.append(max_temp)
    if len(temp_history) >= 2:
        temp_diff = round(temp_history[-1] - temp_history[-2], 3)
    else:
        temp_diff = 0.0

    temp_avg5 = round(float(np.mean(list(temp_history))), 2)
    temp_max5 = round(float(np.max(list(temp_history))), 2)

    features = np.array([[max_temp, avg_temp, temp_diff, temp_avg5, temp_max5]])
    status = model_temp.predict(features)[0]
    proba  = model_temp.predict_proba(features)[0]
    classes = list(model_temp.classes_)

    if "FEVER" in classes:
        fever_risk = round(proba[classes.index("FEVER")] * 100, 1)
    else:
        fever_risk = 0.0

    return status, fever_risk


def predict_ammonia(nh3_ppm, temp, humidity=65, pig_count=5):
    global model_nh3
    if model_nh3 is None:
        if nh3_ppm >= 35:
            return "DANGER"
        elif nh3_ppm >= 25:
            return "WARNING"
        return "SAFE"
    features = np.array([[nh3_ppm, temp, humidity, pig_count]])
    return model_nh3.predict(features)[0]


def predict_activity(stats):
    global model_activity, prev_zone, zone_changes
    if model_activity is None:
        return "ACTIVE"

    temp_history_list = list(temp_history)
    if len(temp_history_list) >= 2:
        temp_var = round(float(np.std(temp_history_list)), 3)
    else:
        temp_var = 0.0

    avg_temp = stats["avg_temp"]
    movement = round(random.uniform(0.1, 0.7), 3)
    current_zone = stats.get("hot_zone", "")
    if prev_zone and current_zone != prev_zone:
        zone_changes += 1
    prev_zone = current_zone

    features = np.array([[temp_var, avg_temp, movement, min(zone_changes, 10)]])
    activity = model_activity.predict(features)[0]
    zone_changes = max(0, zone_changes - 1)
    return activity


def get_trend():
    if len(temp_history) < 3:
        return "Collecting data..."
    recent = list(temp_history)[-3:]
    diff = recent[-1] - recent[0]
    if diff > 0.5:   return "Rising rapidly"
    if diff > 0.2:   return "Rising slowly"
    if diff < -0.5:  return "Falling rapidly"
    if diff < -0.2:  return "Falling slowly"
    return "Stable"
