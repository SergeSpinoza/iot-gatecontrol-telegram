from umqtt.robust import MQTTClient
from machine import Pin
from machine import Timer
from machine import WDT
import network
import machine
import ubinascii
import utime as time
import usocket as socket
import ustruct as struct
import uasyncio as asyncio
import webrepl
import urandom
import gc
import config

wdt = WDT()
gc.enable()

### Variables
int_err_count = 0
ping_mqtt = 0
ping_fail = 0
# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
ntp_delta = 3155673600
host = "pool.ntp.org"

# Setup a GPIO Pin for output
bulbPin = Pin(4, Pin.OUT)


def activate():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(config.CONFIG['WIFI_SSID'], config.CONFIG['WIFI_PASSWORD'])
        while not wlan.isconnected():
            pass
        print('network config:', wlan.ifconfig())
    # Disable integration wifi point (MicroPython)
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)


def time_now():
    ntp_query = bytearray(48)
    ntp_query[0] = 0x1b
    try:
        addr = socket.getaddrinfo(host, 123)[0][-1]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.sendto(ntp_query, addr)
        msg = s.recv(48)
        s.close()
        val = struct.unpack("!I", msg[40:44])[0]
        return val - ntp_delta
    except Exception as error:
        print("Error: [Exception] %s: %s" % (type(error).__name__, error))
        time.sleep(60)
        machine.reset()


def settime():
    try:
        t = time_now()
        tm = time.localtime(t)
        tm = tm[0:3] + (0,) + tm[3:6] + (0,)
        machine.RTC().datetime(tm)
    except Exception as error:
        print("Error: [Exception] %s: %s" % (type(error).__name__, error))
        time.sleep(60)
        machine.reset()


activate()
webrepl.start()
settime()


# Check Internet connection
def internet_connected(host='8.8.8.8', port=53):
    global int_err_count
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            int_err_count = 0
            return True
        except Exception as error:
            print("Error Internet connect: [Exception] %s: %s" % (type(error).__name__, error))
            return False
        finally:
            s.close()


# Method to act based on message received
def onMessage(topic, msg):
    global ping_fail
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
            client.publish(config.CONFIG['TOPIC'], send_msg)
    elif str(msg).find("PING-") > -1:
        msg = str(msg)
        msg = msg.replace('b', '').replace('\'', '').replace("\"", "")
        msg_list = msg.split('-')
        if msg_list[1]:
            send_msg = "PONG-" + str(msg_list[1])
            client.publish(config.CONFIG['TOPIC'], send_msg)
    elif msg == b"RESET":
        machine.reset()
    elif str(msg).find("ECHO-") > -1:
        print("MQTT pong true...")
        ping_fail = 0


def mqtt_reconnect():
    # Create an instance of MQTTClient
    global client
    try:
        client = MQTTClient(config.CONFIG['CLIENT_ID'], config.CONFIG['MQTT_BROKER'], user=config.CONFIG['USER'], password=config.CONFIG['PASSWORD'], port=config.CONFIG['PORT'])
        # Attach call back handler to be called on receiving messages
        # client.DEBUG = True
        client.set_callback(onMessage)
        client.connect(clean_session=True)
        client.subscribe(config.CONFIG['TOPIC'])
        print("ESP8266 is Connected to %s and subscribed to %s topic" % (config.CONFIG['MQTT_BROKER'], config.CONFIG['TOPIC']))
    except Exception as error:
        print("Error in MQTT reconnection: [Exception] %s: %s" % (type(error).__name__, error))


# Check MQTT brocker
async def mqtt_check():
    global ping_fail
    global ping_mqtt
    while True:
        await asyncio.sleep(10)
        # ping_mqtt = time.time()
        rand = urandom.getrandbits(30)
        send_msg = "ECHO-" + str(rand)
        client.publish(config.CONFIG['TOPIC'], send_msg)
        # client.publish(device_topic + "state/check/mqtt", "%s" % ping_mqtt)
        print("Send MQTT ping (%s)" % send_msg)
        ping_fail += 1

        if ping_fail >= config.CONFIG['MQTT_CRIT_ERR']:
            print("MQTT ping false... reset (%i)" % ping_fail)
            machine.reset()

        if ping_fail >= config.CONFIG['MQTT_MAX_ERR']:
            print("MQTT ping false... reconnect (%i)" % ping_fail)
            client.disconnect()
            mqtt_reconnect()


# Check MQTT message
async def check_message():
    while True:
        await asyncio.sleep(1)
        print("Check message...")
        try:
            client.check_msg()
        except Exception as error:
            print("Error in mqtt check message: [Exception] %s: %s" % (type(error).__name__, error))
            mqtt_reconnect()
        wdt.feed()


# Check Internet connected and reconnect
async def check_internet():
    global int_err_count
    try:
        while True:
            await asyncio.sleep(60)
            print("Check Internet connect... ")
            if not internet_connected():
                print("Internet connect fail...")
                int_err_count += 1

                if int_err_count >= config.CONFIG['INT_CRIT_ERR']:
                    client.disconnect()
                    wifi.wlan.disconnect()
                    machine.reset()

                if int_err_count >= config.CONFIG['INT_MAX_ERR']:
                    print("Internet reconnect")
                    client.disconnect()
                    wifi.wlan.disconnect()
                    wifi.activate()
    except Exception as error:
        print("Error in Internet connection: [Exception] %s: %s" % (type(error).__name__, error))


mqtt_reconnect()
try:
    loop = asyncio.get_event_loop()
    loop.create_task(check_message())
    loop.create_task(check_internet())
    loop.create_task(mqtt_check())
    loop.run_forever()
except Exception as e:
    print("Error: [Exception] %s: %s" % (type(e).__name__, e))
    time.sleep(60)
    machine.reset()

# client.disconnect()



