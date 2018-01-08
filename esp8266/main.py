from umqtt.robust import MQTTClient
from machine import Pin
import network
import machine
import ubinascii
import utime as time
import usocket as socket
import ustruct as struct
import webrepl

def activate():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect('wifi-ssid', 'password')
        while not wlan.isconnected():
            pass
        print('network config:', wlan.ifconfig())
    # Disable integration wifi point (MicroPython)
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)

activate()
webrepl.start()

# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
NTP_DELTA = 3155673600
host = "pool.ntp.org"

def time_now():
    NTP_QUERY = bytearray(48)
    NTP_QUERY[0] = 0x1b
    addr = socket.getaddrinfo(host, 123)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1)
    res = s.sendto(NTP_QUERY, addr)
    msg = s.recv(48)
    s.close()
    val = struct.unpack("!I", msg[40:44])[0]
    return val - NTP_DELTA

# There's currently no timezone support in MicroPython, so
# utime.localtime() will return UTC time (as if it was .gmtime())
def settime():
    t = time_now()
    tm = time.localtime(t)
    tm = tm[0:3] + (0,) + tm[3:6] + (0,)
    machine.RTC().datetime(tm)
    # print(time.localtime())

settime()

# Setup a GPIO Pin for output
bulbPin = Pin(4, Pin.OUT)

# Check Internet connection
def internet_connected(host='8.8.8.8', port=53):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((host, port))
        return True
    except:
        return False
    finally:
        s.close()

# Modify below section as required
CONFIG = {
    # Configuration details of the MQTT broker
    "MQTT_BROKER": "host",
    "USER": "mqtt_user",
    "PASSWORD": "password",
    "PORT": 16375,
    "TOPIC": b"street/gate1", # or street/gate2 and street/garage, depending on which controller is configured
    # unique identifier of the chip
    "CLIENT_ID": b"esp8266_gate_" + ubinascii.hexlify(machine.unique_id())
}

# Method to act based on message received
def onMessage(topic, msg):
    print("Topic: %s, Message: %s" % (topic, msg))
    if str(msg).find("SIGNAL-") > -1:
        bulbPin.on()
        time.sleep(0.6)
        bulbPin.off()
        msg = str(msg)
        msg = msg.replace('b', '').replace('\'', '').replace("\"", "")
        msg_list = msg.split('-')
        if msg_list[1]:
            send_msg = "SIGNALOK-" + str(msg_list[1])
            client.publish(CONFIG['TOPIC'], send_msg)
    elif str(msg).find("PING-") > -1:
        msg = str(msg)
        msg = msg.replace('b', '').replace('\'', '').replace("\"", "")
        msg_list = msg.split('-')
        if msg_list[1]:
            send_msg = "PONG-" + str(msg_list[1])
            client.publish(CONFIG['TOPIC'], send_msg)
    elif msg == b"RESET":
        machine.reset()

def mqtt_reconnect():
    # Create an instance of MQTTClient
    global client
    client = MQTTClient(CONFIG['CLIENT_ID'], CONFIG['MQTT_BROKER'], user=CONFIG['USER'], password=CONFIG['PASSWORD'], port=CONFIG['PORT'])
    # Attach call back handler to be called on receiving messages
    client.DEBUG = True
    client.set_callback(onMessage)
    client.connect(clean_session=True)
    client.subscribe(CONFIG['TOPIC'])
    print("ESP8266 is Connected to %s and subscribed to %s topic" % (CONFIG['MQTT_BROKER'], CONFIG['TOPIC']))

i = 2
try:
    while True:
        ping_test = internet_connected()
        if ping_test and i == 0:
            # Check topic
            client.check_msg()
        elif ping_test and i == 1:
            # New session
            mqtt_reconnect()
            client.check_msg()
            i = 0
        elif ping_test == False and i == 0:
            # Disconnect
            i = 1
            client.disconnect()
        elif ping_test and i == 2:
            # First connection
            mqtt_reconnect()
            i = 0
        else:
            # No Internet Connection
            pass
        time.sleep(0.5)
        continue
except OSError as e:
    print(e)
    time.sleep(60)
    machine.reset()

client.disconnect()



