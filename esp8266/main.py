from umqtt.robust import MQTTClient
from machine import Pin
from machine import Timer
import network
import machine
import ubinascii
import utime as time
import usocket as socket
import ustruct as struct
import webrepl
import urandom

global i
global echo_msg_req
global echo_msg_ans
global echo_fails
echo_msg_req = "EMPTY"
echo_msg_ans = "EMPTY"
echo_fails = 0
tim_1 = Timer(-1)
i = 2
# Setup a GPIO Pin for output
bulbPin = Pin(4, Pin.OUT)

# These defaults are overwritten with the contents of config.json by load_config()
CONFIG = {
    # Configuration details of the WiFi network
    "WIFI_SSID": "network_ssid",
    "WIFI_PASSWORD": "secret_pass",
    # Configuration details of the MQTT broker
    "MQTT_BROKER": "192.168.1.1",
    "USER": "mqtt_user",
    "PASSWORD": "mqtt_pass",
    "PORT": 1883,
    "PORT-SSL": 8883, # ssl port
    "TOPIC": b"mqtt_topic",
    # unique identifier of the chip
    "CLIENT_ID": b"esp8266_" + ubinascii.hexlify(machine.unique_id())
}


def load_config():
    import ujson as json
    try:
        with open("config.json") as f:
            config = json.loads(f.read())
    except (OSError, ValueError):
        print("Couldn't load config.json")
        save_config()
    else:
        CONFIG.update(config)
        print("Loaded config from config.json")

def save_config():
    import ujson as json
    try:
        with open("config.json", "w") as f:
            f.write(json.dumps(CONFIG))
    except OSError:
        print("Couldn't save config.json")

def activate():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('connecting to network...')
        wlan.connect(CONFIG['WIFI_SSID'], CONFIG['WIFI_PASSWORD'])
        while not wlan.isconnected():
            pass
        print('network config:', wlan.ifconfig())
    # Disable integration wifi point (MicroPython)
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)

# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
ntp_delta = 3155673600
host = "pool.ntp.org"

def time_now():
    ntp_query = bytearray(48)
    ntp_query[0] = 0x1b
    addr = socket.getaddrinfo(host, 123)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1)
    res = s.sendto(ntp_query, addr)
    msg = s.recv(48)
    s.close()
    val = struct.unpack("!I", msg[40:44])[0]
    return val - ntp_delta

# There's currently no timezone support in MicroPython, so
# utime.localtime() will return UTC time (as if it was .gmtime())
def settime():
    t = time_now()
    tm = time.localtime(t)
    tm = tm[0:3] + (0,) + tm[3:6] + (0,)
    machine.RTC().datetime(tm)
    # print(time.localtime())

load_config()
activate()
webrepl.start()
try:
    settime()
except OSError as e:
    print(e)
    time.sleep(60)
    machine.reset()

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
    elif str(msg).find("ECHO-") > -1:
        global echo_msg_ans
        msg = str(msg)
        echo_msg_ans = msg.replace('b', '').replace('\'', '').replace("\"", "")
        # print("ECHO msg ans: " + echo_msg_ans)

def mqtt_reconnect():
    # Create an instance of MQTTClient
    global client
    global i
    global echo_fails
    i = 1
    client = MQTTClient(CONFIG['CLIENT_ID'], CONFIG['MQTT_BROKER'], user=CONFIG['USER'], password=CONFIG['PASSWORD'], port=CONFIG['PORT'])
    # Attach call back handler to be called on receiving messages
    client.DEBUG = True
    client.set_callback(onMessage)
    try:
        client.connect(clean_session=True)
        client.subscribe(CONFIG['TOPIC'])
        print("ESP8266 is Connected to %s and subscribed to %s topic" % (CONFIG['MQTT_BROKER'], CONFIG['TOPIC']))
        i = 0
        echo_fails = 0
    except:
        i = 1

def mqtt_check_conn():
    global echo_msg_ans
    global echo_msg_req
    global echo_fails
    global i
    # print("I in func is: " + str(i))
    if i == 0:
        if echo_msg_req != echo_msg_ans:
            echo_fails = 1
            # print("ECHO fails: " + str(echo_fails))
        else:
            echo_fails = 0
            # print("Echo_fails: " + str(echo_fails))
        rand = urandom.getrandbits(30)
        echo_msg_req = "ECHO-" + str(rand)
        client.publish(CONFIG['TOPIC'], echo_msg_req)
        # print("ECHO msg req: " + echo_msg_req)

tim_1.init(period=10000, mode=Timer.PERIODIC, callback=lambda t: mqtt_check_conn())


try:
    while True:
        ping_test = internet_connected()
        if (ping_test and i == 0) and echo_fails == 0:
            # Check topic
            client.check_msg()
        elif ping_test and i == 1:
            # New session, and if Internet is ok but MQTT server not answer
            mqtt_reconnect()
            if i == 0:
                client.check_msg()
        elif (ping_test == False and i == 0) or echo_fails == 1:
            # Disconnect
            echo_msg_ans = echo_msg_req
            if i == 0:
                client.disconnect()
                # print("Client Disconnect")
            i = 1
            # print("Client Disconnected")
        elif ping_test and i == 2:
            # First connection
            mqtt_reconnect()
            i = 0
        else:
            # No Internet Connection
            pass
        time.sleep(0.5)
        continue
except KeyboardInterrupt:
    tim_1.deinit()
except OSError as e:
    print(e)
    time.sleep(60)
    machine.reset()

client.disconnect()
