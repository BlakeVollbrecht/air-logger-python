import time
import board
import busio
import adafruit_bme680
import smbus2
import mysql.connector
from datetime import datetime


def wake_sunrise():
    """Wake the sensor by sending address + STOP (no ACK expected)."""
    try:
        bus.write_byte(sunrise_addr)  # This triggers wake but may raise error (normal)
    except:
        pass  # Ignore, as no ACK
    time.sleep(0.005)

def read_co2():
    """Read filtered CO2 (ppm) from registers 0x06-0x07."""
    wake_sunrise()
    try:
        msb = bus.read_byte_data(sunrise_addr, 0x06)
        lsb = bus.read_byte_data(sunrise_addr, 0x07)
        co2 = (msb << 8) | lsb
        if co2 > 0x7FFF:  # Signed 16-bit handling (unlikely for CO2)
            co2 -= 0x10000
        return co2
    except Exception as e:
        print(f"Sunrise read error: {e}")
        return None


i2c = busio.I2C(board.SCL, board.SDA)

# BME688 setup (uses BME680 library)
bme = adafruit_bme680.Adafruit_BME680_I2C(i2c, debug=False)
bme.sea_level_pressure = 1013.25  # Adjust for your location (hPa)

# Sensair Sunrise setup
sunrise_addr = 0x68
bus = smbus2.SMBus(1)  # I2C bus 1
time.sleep(1)  # Bus settling
wake_sunrise()
try:
    # this configuration should persist after setting one time and restarting sensor module
    bus.write_byte_data(sunrise_addr, 0x96, 0x00)
    bus.write_byte_data(sunrise_addr, 0x97, 0x1E) # configure 30 second measurement interval
except Exception as e:
    print(f"Sunrise write error: {e}")

# Database setup
conn = mysql.connector.connect(
    host='localhost',
    user='grafana',  # automatically suffixed by "@localhost"
    password='strongpassword',
    database='airmetrics'
)
cursor = conn.cursor()

# Main loop for time-series logging
interval = 30   # seconds
while True:    
    # Read Sunrise CO2
    co2 = read_co2()
    
    # Read BME688
    try:
        temp = bme.temperature
        hum = bme.relative_humidity
        press = bme.pressure
        gas = bme.gas
    except Exception as e:
        print(f"BME read error: {e}")
        temp = hum = press = gas = None
        co2 = None  # Retry next cycle
    
    # Save to db
    if co2 is not None and temp is not None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = """
            INSERT INTO readings (timestamp, co2_ppm, temperature_c, humidity_pct, pressure_hpa, gas_ohms)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (timestamp, co2, temp, hum, press, gas))
        conn.commit()

    time.sleep(interval)
