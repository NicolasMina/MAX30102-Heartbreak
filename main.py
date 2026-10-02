from max30102 import MAX30102, MAX30105_PULSE_AMP_MEDIUM
from machine import SoftI2C, Pin
from utime import ticks_diff, ticks_us, ticks_ms, sleep_ms
import network
from umqtt.simple import MQTTClient

# ---------- Configuracion de red y MQTT ----------
SSID = "IPESMI TECNICO"
PASSWORD = "tecnico25"
BROKER = "172.21.0.244"
TOPIC = b"habitacion1/paciente1/bpm"
TOPIC_TEMP = b"habitacion1/paciente1/temp"
CLIENT_ID = "esp32_hab1"

# ---------- WiFi ----------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)
while not wlan.isconnected():
    sleep_ms(500)
print("WiFi OK:", wlan.ifconfig())


# ---------- MQTT ----------
def publish_value(topic, value):
    if value <= 0:
        return

    payload = str(value).encode("utf-8")
    try:
        client.publish(topic, payload)
    except OSError:
        print("Error MQTT, reconectando...")
        try:
            client.connect()
            client.publish(topic, payload)
        except OSError:
            print("No se pudo reconectar al broker MQTT")


client = MQTTClient(CLIENT_ID, BROKER, port=1883)
client.connect()
print("MQTT conectado")
client.publish(TOPIC, b"test")
print("Test enviado")

# ---------- Sensor ----------
led = Pin(2, Pin.OUT)

MAX_HISTORY = 32
history = []
beats_history = []
beat = False
beats = 0

i2c = SoftI2C(sda=Pin(21), scl=Pin(22), freq=400000)
scan_result = i2c.scan()
print("I2C scan:", scan_result)
sensor = MAX30102(i2c=i2c)

if sensor.i2c_address not in scan_result:
    print("Sensor not found.")
    print("Comprueba: SDA=GPIO21, SCL=GPIO22, VDD=3.3V, GND, pull-ups 4.7k en SDA/SCL.")
    while True:
        sleep_ms(1000)
elif not (sensor.check_part_id()):
    print("I2C device ID not corresponding to MAX30102 or MAX30105.")
    while True:
        sleep_ms(1000)
else:
    print("Sensor connected and recognized.")

print("Setting up sensor with default configuration.", '\n')
sensor.setup_sensor()

sensor.set_sample_rate(400)
sensor.set_fifo_average(8)
sensor.set_active_leds_amplitude(MAX30105_PULSE_AMP_MEDIUM)
sensor.set_led_mode(2)
sleep_ms(1000)

print("Reading temperature in C.", '\n')
print(sensor.read_temperature())

t_start = ticks_us()
last_pub = ticks_ms()
last_temp = ticks_ms()

# ---------- Bucle principal ----------
while True:
    # Cada 2 segundos: mostrar y publicar el BPM
    if ticks_diff(ticks_ms(), last_pub) > 2000:
        last_pub = ticks_ms()
        print(beats)
        if beats > 0:
            publish_value(TOPIC, beats)

    # Cada 5 segundos: leer y publicar la temperatura (del chip, no corporal)
    if ticks_diff(ticks_ms(), last_temp) > 5000:
        last_temp = ticks_ms()
        temp = round(sensor.read_temperature(), 2)
        print("Temp:", temp)
        publish_value(TOPIC_TEMP, temp)

    sensor.check()

    if sensor.available():
        red_reading = sensor.pop_red_from_storage()
        ir_reading = sensor.pop_ir_from_storage()

        value = red_reading
        history.append(value)
        history = history[-MAX_HISTORY:]

        minima, maxima = min(history), max(history)

        threshold_on = (minima + maxima * 3) // 4   # 3/4
        threshold_off = (minima + maxima) // 2      # 1/2

        if value > 1000:
            if not beat and value > threshold_on:
                beat = True
                led.on()
                t_us = ticks_diff(ticks_us(), t_start)
                t_s = t_us / 1000000
                if t_s > 0:
                    f = 1 / t_s
                    bpm = f * 60
                    if bpm < 500:
                        t_start = ticks_us()
                        beats_history.append(bpm)
                        beats_history = beats_history[-MAX_HISTORY:]
                        beats = round(sum(beats_history) / len(beats_history), 2)
            if beat and value < threshold_off:
                beat = False
                led.off()
        else:
            led.off()
            print('Not finger')
