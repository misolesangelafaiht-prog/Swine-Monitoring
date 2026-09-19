import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

VCC = 5.0
RL = 20.0
CLEAN_AIR_RATIO = 3.6  # Rs/R0 ratio in clean air, per MQ-135 datasheet

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=0x48)
ads.gain = 2 / 3
chan = AnalogIn(ads, 0)

print("Let the sensor warm up in clean, open air for 60 seconds...")
time.sleep(60)

readings = []
for i in range(20):
    v = chan.voltage
    rs = (VCC - v) * RL / v
    readings.append(rs)
    print("Reading " + str(i + 1) + ": Rs = " + str(round(rs, 2)))
    time.sleep(1)

avg_rs = sum(readings) / len(readings)
r0 = avg_rs / CLEAN_AIR_RATIO
print("---")
print("Average Rs: " + str(round(avg_rs, 2)))
print("Calculated R0: " + str(round(r0, 2)))
print("Copy this R0 value into ammonia.py")
