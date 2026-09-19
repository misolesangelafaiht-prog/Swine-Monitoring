import urllib.request
import urllib.parse
import os
import time
import json
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8604979728:AAEg7GaDrZ8ZJiuqr2X4Hd8kPWcM1vVU9S8"
THINGSPEAK_API_KEY = "T8BOQ01CICS3SEJR"
THINGSPEAK_URL = "https://api.thingspeak.com/update"
TELEGRAM_URL = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN

SUBSCRIBERS_FILE = "/home/pi/swine_monitor/subscribers.json"

# ── Separate cooldown for each alert type ──────────────────────
# Each alert type has its OWN cooldown timer
# So removing and reapplying heat triggers a new alert
# after the cooldown for that specific type expires
ALERT_COOLDOWN = 120  # 2 minutes per alert type

last_alert_times = {
    "fever_only"          : 0,
    "ammonia_only"        : 0,
    "activity_only"       : 0,
    "fever_ammonia"       : 0,
    "fever_activity"      : 0,
    "ammonia_activity"    : 0,
    "all_critical"        : 0,
}

last_ts_time   = 0
last_update_id = 0

# ── Track previous status to detect changes ────────────────────
prev_fever_state    = False
prev_ammonia_state  = False
prev_activity_state = False


def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_subscribers(subs):
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(subs, f)
    except Exception as e:
        print("[cloud] Save error: " + str(e))


def send_message_to(chat_id, message):
    try:
        url = TELEGRAM_URL + "/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text"   : message
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("[cloud] Message error: " + str(e))


def check_new_subscribers():
    global last_update_id
    try:
        url = TELEGRAM_URL + "/getUpdates?offset=" + str(last_update_id + 1) + "&timeout=1"
        response = urllib.request.urlopen(url, timeout=5).read().decode()
        data = json.loads(response)
        if not data.get("ok"):
            return
        updates = data.get("result", [])
        subs = load_subscribers()
        changed = False
        for update in updates:
            last_update_id = update["update_id"]
            message = update.get("message", {})
            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))
            text = message.get("text", "")
            first_name = chat.get("first_name", "User")
            if chat_id and chat_id not in subs:
                subs.append(chat_id)
                changed = True
                print("[cloud] New subscriber: " + first_name)
                welcome = "Hello " + first_name + "!\n"
                welcome += "You are subscribed to SwineGuard Monitor.\n"
                welcome += "You will receive specific alerts for:\n"
                welcome += "  High body temperature (fever)\n"
                welcome += "  High ammonia levels\n"
                welcome += "  Abnormal pig activity\n"
                welcome += "  Any combination of the above\n\n"
                welcome += "/stop - Unsubscribe\n"
                welcome += "/status - Check system status"
                send_message_to(chat_id, welcome)
            elif text == "/stop" and chat_id in subs:
                subs.remove(chat_id)
                changed = True
                send_message_to(chat_id, "You have been unsubscribed.")
            elif text == "/status":
                send_message_to(chat_id, "SwineGuard Monitor is running normally.")
        if changed:
            save_subscribers(subs)
    except Exception as e:
        print("[cloud] Subscriber check error: " + str(e))


# ── Message builders ───────────────────────────────────────────

def header(title, max_temp, nh3_ppm, activity_score, hot_zone, trend):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg  = "[" + title + "]\n\n"
    msg += "Body Temp     : " + str(max_temp) + "C\n"
    msg += "Ammonia Level : " + str(nh3_ppm) + " ppm\n"
    msg += "Activity Score: " + str(round(activity_score, 2)) + "\n"
    msg += "Hot Zone      : " + hot_zone + "\n"
    msg += "Trend         : " + trend + "\n"
    msg += "Time          : " + now + "\n"
    return msg


def fever_recommendations():
    msg  = "\n--- FEVER RECOMMENDATIONS ---\n"
    msg += "\n1. ISOLATE IMMEDIATELY\n"
    msg += "   Separate pig from herd into quarantine.\n"
    msg += "   Reduces pathogen transmission.\n"
    msg += "   [Laanen et al., 34]\n"
    msg += "\n2. CALL VETERINARIAN\n"
    msg += "   Early treatment during febrile stage\n"
    msg += "   improves recovery outcomes.\n"
    msg += "   [Loving et al., 39]\n"
    msg += "\n3. SUPPORTIVE CARE\n"
    msg += "   Provide clean water and electrolytes.\n"
    msg += "   Give easily digestible feed.\n"
    msg += "   NSAIDs under vet supervision for fever.\n"
    msg += "   [Pensaert and Vandeputte, 40]\n"
    msg += "\n4. DISINFECT AFTER RECOVERY\n"
    msg += "   Clean quarantine area and all equipment\n"
    msg += "   with virucidal agents. [Dewulf et al., 35]\n"
    msg += "\n5. CHECK VACCINATION\n"
    msg += "   Review H1N1, H1N2, H3N2 vaccine program.\n"
    msg += "   [Crisci et al., 41]\n"
    msg += "\n6. REPORT IF ZOONOTIC\n"
    msg += "   Report to animal health authorities.\n"
    msg += "   [WOAH, 31]\n"
    return msg


def ammonia_recommendations():
    msg  = "\n--- AMMONIA RECOMMENDATIONS ---\n"
    msg += "\n1. INCREASE VENTILATION NOW\n"
    msg += "   Open vents and activate exhaust fans.\n"
    msg += "   Most effective NH3 control method.\n"
    msg += "   [Donham, 33]\n"
    msg += "\n2. REMOVE MANURE AND WASTE\n"
    msg += "   Clean pens, drains, and storage areas.\n"
    msg += "   Twice-daily cleaning reduces NH3 by 40%.\n"
    msg += "   [Philippe and Nicks, 42]\n"
    msg += "\n3. REDUCE STOCKING DENSITY\n"
    msg += "   Overcrowding increases ammonia buildup.\n"
    msg += "   [Donham, 33]\n"
    msg += "\n4. REVIEW DIETARY PROTEIN\n"
    msg += "   Optimize feed protein to reduce\n"
    msg += "   nitrogen excretion. [Zhuang et al., 24]\n"
    msg += "\n5. VETERINARY CHECK OF HERD\n"
    msg += "   Prolonged exposure increases risk of\n"
    msg += "   swine influenza and Mycoplasma.\n"
    msg += "   [Liu et al., 23]\n"
    return msg


def activity_recommendations():
    msg  = "\n--- ACTIVITY RECOMMENDATIONS ---\n"
    msg += "\nNote: Reduced activity may appear 24-48hrs\n"
    msg += "before clinical symptoms. [Gonzalez, 25]\n"
    msg += "\n1. OBSERVE BEHAVIOR\n"
    msg += "   Check: feeding, water intake, posture,\n"
    msg += "   social interaction, respiratory rate.\n"
    msg += "   [Fraser et al., 32]\n"
    msg += "\n2. PHYSICAL INSPECTION\n"
    msg += "   Check for: respiratory distress, nasal\n"
    msg += "   discharge, conjunctivitis, lameness.\n"
    msg += "   [Ni et al., 14]\n"
    msg += "\n3. VETERINARY EVALUATION\n"
    msg += "   Low activity + reduced feed intake\n"
    msg += "   is high-risk. Contact vet promptly.\n"
    msg += "   [Gonzalez-Sanchez et al., 25]\n"
    msg += "\n4. ISOLATE IF DISEASE CONFIRMED\n"
    msg += "   Minimize transmission to herd.\n"
    msg += "   [Dewulf and Van Immerseel, 35]\n"
    return msg


# ── 7 specific alert messages ──────────────────────────────────

def msg_fever_only(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("FEVER ALERT — HIGH TEMPERATURE ONLY",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "Fever Risk    : " + str(fever_risk) + "%\n"
    msg += "\nAmmonia    : NORMAL (safe)\n"
    msg += "Activity   : NORMAL (active)\n"
    msg += "\nOnly body temperature is elevated.\n"
    msg += "Focus on fever management.\n"
    msg += fever_recommendations()
    return msg


def msg_ammonia_only(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("AMMONIA ALERT — HIGH AMMONIA ONLY",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "\nTemperature: NORMAL (no fever)\n"
    msg += "Activity   : NORMAL (active)\n"
    msg += "\nOnly ammonia is elevated.\n"
    msg += "No fever detected. Focus on air quality.\n"
    msg += ammonia_recommendations()
    return msg


def msg_activity_only(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("ACTIVITY ALERT — ABNORMAL BEHAVIOR ONLY",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "\nTemperature: NORMAL (no fever)\n"
    msg += "Ammonia    : NORMAL (safe)\n"
    msg += "\nOnly activity is abnormal.\n"
    msg += "Could be early disease sign or stress.\n"
    msg += "Monitor closely. [Gonzalez-Sanchez, 25]\n"
    msg += activity_recommendations()
    return msg


def msg_fever_ammonia(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("ALERT — HIGH TEMPERATURE + HIGH AMMONIA",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "Fever Risk    : " + str(fever_risk) + "%\n"
    msg += "\nActivity   : NORMAL (active)\n"
    msg += "\nFever and high ammonia detected together.\n"
    msg += "High ammonia weakens respiratory defenses\n"
    msg += "and worsens fever-related illness.\n"
    msg += "[Liu et al., 23]\n"
    msg += fever_recommendations()
    msg += ammonia_recommendations()
    return msg


def msg_fever_activity(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("ALERT — HIGH TEMPERATURE + LOW ACTIVITY",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "Fever Risk    : " + str(fever_risk) + "%\n"
    msg += "\nAmmonia    : NORMAL (safe)\n"
    msg += "\nFever and abnormal activity detected.\n"
    msg += "Low activity during fever strongly indicates\n"
    msg += "active disease onset. Urgent action needed.\n"
    msg += "[Schaefer et al., 15], [Gonzalez, 25]\n"
    msg += fever_recommendations()
    msg += activity_recommendations()
    return msg


def msg_ammonia_activity(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("ALERT — HIGH AMMONIA + LOW ACTIVITY",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "\nTemperature: NORMAL (no fever yet)\n"
    msg += "\nHigh ammonia and low activity detected.\n"
    msg += "No fever yet but this combination suggests\n"
    msg += "early respiratory stress or disease onset.\n"
    msg += "Monitor temperature closely.\n"
    msg += "[Liu et al., 23], [Gonzalez, 25]\n"
    msg += ammonia_recommendations()
    msg += activity_recommendations()
    return msg


def msg_all_critical(max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend):
    msg  = header("CRITICAL ALERT — ALL INDICATORS AT RISK",
                  max_temp, nh3_ppm, activity_score, hot_zone, trend)
    msg += "Fever Risk    : " + str(fever_risk) + "%\n"
    msg += "\nALL THREE INDICATORS ARE ABNORMAL:\n"
    msg += "  Temperature : HIGH (" + str(max_temp) + "C)\n"
    msg += "  Ammonia     : HIGH (" + str(nh3_ppm) + " ppm)\n"
    msg += "  Activity    : LOW  (" + str(round(activity_score, 2)) + ")\n"
    msg += "\nThis is the highest risk condition.\n"
    msg += "Immediate action required.\n"
    msg += fever_recommendations()
    msg += ammonia_recommendations()
    msg += activity_recommendations()
    return msg


# ── Main alert dispatcher ──────────────────────────────────────

def send_telegram_alert(max_temp, fever_risk, status, trend,
                        hot_zone, nh3_ppm=0, activity_score=1.0):
    global last_alert_times, prev_fever_state
    global prev_ammonia_state, prev_activity_state

    now = time.time()

    # Determine which indicators are at risk
    fever_alert    = max_temp >= 40.5 or status in ["FEVER", "ELEVATED"]
    ammonia_alert  = nh3_ppm >= 25
    activity_alert = activity_score <= 0.4

    # Detect state CHANGES — retrigger when condition returns then spikes again
    fever_changed    = fever_alert    != prev_fever_state
    ammonia_changed  = ammonia_alert  != prev_ammonia_state
    activity_changed = activity_alert != prev_activity_state

    prev_fever_state    = fever_alert
    prev_ammonia_state  = ammonia_alert
    prev_activity_state = activity_alert

    # Nothing at risk
    if not fever_alert and not ammonia_alert and not activity_alert:
        return False

    subs = load_subscribers()
    if not subs:
        print("[cloud] No subscribers")
        return False

    # Determine which alert type and message to send
    alert_key = None
    message   = None

    if fever_alert and ammonia_alert and activity_alert:
        alert_key = "all_critical"
        message   = msg_all_critical(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif fever_alert and ammonia_alert and not activity_alert:
        alert_key = "fever_ammonia"
        message   = msg_fever_ammonia(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif fever_alert and not ammonia_alert and activity_alert:
        alert_key = "fever_activity"
        message   = msg_fever_activity(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif not fever_alert and ammonia_alert and activity_alert:
        alert_key = "ammonia_activity"
        message   = msg_ammonia_activity(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif fever_alert and not ammonia_alert and not activity_alert:
        alert_key = "fever_only"
        message   = msg_fever_only(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif not fever_alert and ammonia_alert and not activity_alert:
        alert_key = "ammonia_only"
        message   = msg_ammonia_only(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    elif not fever_alert and not ammonia_alert and activity_alert:
        alert_key = "activity_only"
        message   = msg_activity_only(
            max_temp, fever_risk, nh3_ppm, activity_score, hot_zone, trend)

    if alert_key is None or message is None:
        return False

    # Check cooldown for this specific alert type
    time_since_last = now - last_alert_times[alert_key]
    if time_since_last < ALERT_COOLDOWN and not fever_changed and not ammonia_changed and not activity_changed:
        remaining = int(ALERT_COOLDOWN - time_since_last)
        print("[cloud] " + alert_key + " cooldown: " + str(remaining) + "s remaining")
        return False

    # Send to all subscribers
    sent = 0
    for chat_id in subs:
        send_message_to(chat_id, message)
        sent += 1

    last_alert_times[alert_key] = now
    print("[cloud] Alert sent: " + alert_key + " to " + str(sent) + " subscribers")
    return True


def send_to_thingspeak(max_temp, avg_temp, fever_risk, status):
    global last_ts_time
    if time.time() - last_ts_time < 15:
        return False
    try:
        params = urllib.parse.urlencode({
            "api_key": THINGSPEAK_API_KEY,
            "field1" : max_temp,
            "field2" : avg_temp,
            "field3" : fever_risk,
            "field4" : 2 if status == "FEVER" else 1 if status == "ELEVATED" else 0,
        })
        result = urllib.request.urlopen(
            THINGSPEAK_URL + "?" + params, timeout=10
        ).read().decode()
        if result != "0":
            last_ts_time = time.time()
            print("[cloud] ThingSpeak updated")
            return True
    except Exception as e:
        print("[cloud] ThingSpeak error: " + str(e))
    return False


def save_to_csv(max_temp, avg_temp, fever_risk, status, trend):
    try:
        path = "/home/pi/swine_monitor/pig_data.csv"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("timestamp,max_temp,avg_temp,fever_risk,status,trend\n")
        with open(path, "a") as f:
            line = (timestamp + "," + str(max_temp) + "," +
                    str(avg_temp) + "," + str(fever_risk) +
                    "," + status + "," + trend)
            f.write(line + "\n")
    except Exception as e:
        print("[cloud] CSV error: " + str(e))


def send_all(max_temp, avg_temp, fever_risk, status, trend,
             hot_zone="Unknown", nh3_ppm=0, activity_score=1.0,
             pig_status="PIG_DETECTED", activity_state="ACTIVE"):

    print("[cloud] Temp:" + str(max_temp) + "C NH3:" +
          str(nh3_ppm) + "ppm Act:" +
          str(round(activity_score, 2)) + " Status:" + status +
          " Pig:" + pig_status + " ActState:" + activity_state)

    check_new_subscribers()
    save_to_csv(max_temp, avg_temp, fever_risk, status, trend)
    send_to_thingspeak(max_temp, avg_temp, fever_risk, status)

    # Do NOT send alert if no pig detected
    if pig_status == "NO_PIG_DETECTED":
        print("[cloud] No pig detected — skipping alert")
        return False

    # Do NOT send alert if pig is just sleeping
    if activity_state in ["SLEEPING", "DEEP_SLEEP"]:
        print("[cloud] Pig is sleeping — skipping alert")
        return False

    # Send alert normally
    send_telegram_alert(
        max_temp, fever_risk, status, trend,
        hot_zone, nh3_ppm, activity_score
    )
