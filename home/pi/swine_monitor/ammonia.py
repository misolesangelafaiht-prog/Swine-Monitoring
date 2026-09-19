import time
import random
import threading

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    LIB_AVAILABLE = True
except ImportError:
    LIB_AVAILABLE = False
    print("[ammonia] ADS1115 library not found — simulation mode active")

_lock = threading.Lock()
_chan = None
SIMULATION_MODE = not LIB_AVAILABLE

VCC = 5.0        # MQ-135 supply voltage
RL = 20.0        # load resistance in kΩ (check your board's silkscreen; common value is 20k)
R0 = 66.31        # calibrated in clean air on [today's date]

def setup_ammonia_sensor():
    global _chan, SIMULATION_MODE
    if not LIB_AVAILABLE:
        return False
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c, address=0x48)
        ads.gain = 2 / 3  # allows reading up to ~6.144V safely
        _chan = AnalogIn(ads, 0)
        print("[ammonia] ADS1115 + MQ-135 ready")
        return True
    except Exception as e:
        print("[ammonia] Setup error: " + str(e) + " — falling back to simulation")
        SIMULATION_MODE = True
        return False


def _read_voltage():
    if _chan is None:
        return None
    try:
        with _lock:
            return _chan.voltage
    except Exception as e:
        print("[ammonia] Read error: " + str(e))
        return None


def _voltage_to_ppm(voltage):
    if voltage is None or voltage <= 0.01:
        return None
    try:
        rs = (VCC - voltage) * RL / voltage
        ratio = rs / R0
        # Empirical NH3 curve approximation (MQ-135 datasheet regression)
        ppm = 116.6020682 * (ratio ** -2.769034857)
        return round(ppm, 1)
    except Exception:
        return None


def get_ammonia_ppm():
    """Returns current NH3 ppm reading, real or simulated."""
    if SIMULATION_MODE or _chan is None:
        return round(10 + random.uniform(0, 15), 1)
    voltage = _read_voltage()
    ppm = _voltage_to_ppm(voltage)
    if ppm is None:
        return round(10 + random.uniform(0, 15), 1)
    return ppm
