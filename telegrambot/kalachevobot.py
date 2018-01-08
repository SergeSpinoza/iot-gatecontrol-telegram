import logging
import paho.mqtt.client as mqttClient
import struct
import socket

import json
import os
import sys
import time
import threading
import datetime
import requests

from enum import Enum, auto
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode
from telegram.ext import Updater, CommandHandler, ConversationHandler, RegexHandler

# Logging
#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('command.log')
fh.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

# MQTT Settings
mqtt_broker = "host"
user = "mqtt_user"
password = "password"
port = 16375
port_ssl = 26375 # ssl port
gate1_topic = "street/gate1"
gate2_topic = "street/gate2"
garage_topic = "street/garage"
mqtt_client_id = "bot_name"
mqtt_qos = 2
mqtt_keepalive = 60
mqtt_tls = True

### Telegram settings
bot_token = 'telegram_bot_token'
# Bot users list
user_id_list = ('1111111111', '22222222222')
#                 user1         user2

### NTP settings
# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
NTP_DELTA = 3155673600
host = "pool.ntp.org"

updater = Updater(token=bot_token)
dispatcher = updater.dispatcher
job_queue = updater.job_queue

### Write command to log
def write_com_log (user_id, command, controller):
    logging.info("User: " + str(user_id) + ", gave the command: " + command + " to controller: " + str(controller))
#    file = open('kalachevobot.log', 'a+')



### MQTT ###

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
        global Connected  # Use global variable
        Connected = True  # Signal connection
    else:
        print("Connection failed")
def on_message(client, userdata, message):
    if str(message.payload).find("PONG") > -1 and message.topic == "street/gate1":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Контроллер GATE 1 на связи.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)
    elif str(message.payload).find("PONG") > -1 and message.topic == "street/gate2":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Контроллер GATE 2 на связи.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)
    elif str(message.payload).find("PONG") > -1 and message.topic == "street/garage":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Контроллер GARAGE на связи.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)
    elif str(message.payload).find("SIGNALOK") > -1 and message.topic == "street/gate1":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Gate 1: команда получена.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)
    elif str(message.payload).find("SIGNALOK") > -1 and message.topic == "street/gate2":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Gate 2: команда получена.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)
    elif str(message.payload).find("SIGNALOK") > -1 and message.topic == "street/garage":
        str_full = str(message.payload).replace('b', '').replace('\'', '').replace('\"', '')
        str_list = str_full.split('-', maxsplit=1)
        t_message = "Garage ворота: команда получена.\n"
        if str_list[1]:
            updater.bot.send_message(str_list[1], t_message)


Connected = False  # global variable for the state of the connection
client = mqttClient.Client(mqtt_client_id)  # create new instance
client.username_pw_set(user, password=password)  # set username and password
client.on_connect = on_connect  # attach function to callback
client.on_message = on_message  # attach function to callback
if mqtt_tls == True:
    client.tls_set("cacert.pem")
    client.connect(mqtt_broker, port=port_ssl)  # connect to broker
else:
    client.connect(mqtt_broker, port=port)  # connect to broker
client.subscribe("street/#")

### END MQTT ###


# Enum for workflow
class WorkflowEnum(Enum):
    GATE1_OPEN_CONFIRM = auto()
    GATE2_OPEN_CONFIRM = auto()
    GARAGE_OPEN_CONFIRM = auto()
    GATE1_GARAGE_OPEN_CONFIRM = auto()
    GATES_SUB_CMD = auto()
    CTRLS_SUB_CMD = auto()
    CTRLS = auto()
    CTRLS_PING = auto()
    CTRLS_RESTART = auto()

# Enum for keyboard
class KeyboardEnum(Enum):
    GATE_1 = auto()
    GATE_2 = auto()
    GARAGE = auto()
    GATE_1_AND_GARAGE = auto()
    PING = auto()
    RESTART = auto()
    YES = auto()
    NO = auto()
    ALL = auto()
    CANCEL = auto()

    def clean(self):
        return self.name.replace("_", " ")

# Time now in sec after 2000, 1, 1
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

# Return chat ID for an update object
def get_chat_id(update=None):
    if update:
        if update.message:
            return update.message.chat_id
        elif update.callback_query:
            return update.callback_query.from_user["id"]
#    else:
#        return user_id


# Check if user is valid and send message to user if not
def is_user_valid(bot, update):
    chat_id = get_chat_id(update)
    found = 0
    for user_id in user_id_list:
        if str(chat_id) == user_id:
            found = 1
            break
#    if str(chat_id) != user_id:
    if found != 1:
        bot.send_message(chat_id, text="Access denied")
        logger.info("Access denied for user %s" % chat_id)
        return False
    else:
        return True

# Create a button menu to show in Telegram messages
def build_menu(buttons, n_cols=1, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)

    return menu

######################
######################
# Custom keyboard that shows all available commands
def keyboard_cmds():
    command_buttons = [
        KeyboardButton("/gates"),
        KeyboardButton("/ctrls")
    ]

    return ReplyKeyboardMarkup(build_menu(command_buttons, n_cols=1))

# Generic custom keyboard that shows YES and NO
def keyboard_confirm():
    buttons = [
        KeyboardButton(KeyboardEnum.YES.clean()),
        KeyboardButton(KeyboardEnum.NO.clean())
    ]

    return ReplyKeyboardMarkup(build_menu(buttons, n_cols=2))

# Cancel function
def cancel(bot, update):
    update.message.reply_text("Отмена...", reply_markup=keyboard_cmds())
    return ConversationHandler.END

# Add asterisk as prefix and suffix for a string
# Will make the text bold if used with Markdown
def bold(text):
    return "*" + text + "*"

#####################
#####################

# Shows sub-commands to control the gates
def gates_cmd(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)

    reply_msg = "Какие ворота вы хотите открыть или закрыть?"

    buttons = [
        KeyboardButton(KeyboardEnum.GATE_1.clean()),
        KeyboardButton(KeyboardEnum.GATE_2.clean()),
        KeyboardButton(KeyboardEnum.GARAGE.clean()),
        KeyboardButton(KeyboardEnum.GATE_1_AND_GARAGE.clean())
    ]

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    reply_mrk = ReplyKeyboardMarkup(build_menu(buttons, n_cols=3, footer_buttons=cancel_btn))
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.GATES_SUB_CMD

# Shows sub-commands to control the controllers
def ctrls_cmd(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)

    reply_msg = "Управление контроллерами. Выберете действие над контроллерами:"

    buttons = [
        KeyboardButton(KeyboardEnum.PING.clean()),
        KeyboardButton(KeyboardEnum.RESTART.clean())
    ]

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    reply_mrk = ReplyKeyboardMarkup(build_menu(buttons, n_cols=3, footer_buttons=cancel_btn))
    update.message.reply_text(reply_msg, reply_markup=reply_mrk)

    return WorkflowEnum.CTRLS_SUB_CMD

# Shows sub-commands to control the controllers
def keyboard_ctrls():
    buttons = [
        KeyboardButton(KeyboardEnum.GATE_1.clean()),
        KeyboardButton(KeyboardEnum.GATE_2.clean()),
        KeyboardButton(KeyboardEnum.GARAGE.clean()),
        KeyboardButton(KeyboardEnum.ALL.clean())
    ]

    cancel_btn = [
        KeyboardButton(KeyboardEnum.CANCEL.clean())
    ]

    return ReplyKeyboardMarkup(build_menu(buttons, n_cols=3, footer_buttons=cancel_btn))


### SUB COMMANDS ####

# GATES SUB commands
def gates_sub_cmd(bot, update):
    # Command to GATE 1
    if update.message.text == KeyboardEnum.GATE_1.clean():
        reply_msg = "Подтвердите действие...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE1_OPEN_CONFIRM
    elif update.message.text == KeyboardEnum.GATE_2.clean():
        reply_msg = "Подтвердите действие...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE2_OPEN_CONFIRM
    elif update.message.text == KeyboardEnum.GARAGE.clean():
        reply_msg = "Подтвердите действие...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GARAGE_OPEN_CONFIRM
    elif update.message.text == KeyboardEnum.GATE_1_AND_GARAGE.clean():
        reply_msg = "Подтвердите действие...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE1_GARAGE_OPEN_CONFIRM
    elif update.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)

# Controllers SUB commands
def ctrls_sub_cmd(bot, update):
    pass
    # Command to CTL 1
    if update.message.text == KeyboardEnum.PING.clean():
        reply_msg = "Выберете контроллер для проверки связи...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_ctrls())
        return WorkflowEnum.CTRLS_PING
    elif update.message.text == KeyboardEnum.RESTART.clean():
        reply_msg = "Выберете контроллер для перезагрузки...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_ctrls())
        return WorkflowEnum.CTRLS_RESTART
    elif update.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)

### CONFIRMATION ###

# Gates confirmation
def gate1_open_confirm(bot, update):
    if update.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(update)
    update.message.reply_text("Подаем команду на GATE 1", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = "SIGNAL-" + str(chat_id)
    client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    # log info
    write_com_log(chat_id, msg_send, "GATE 1")
    #
    return ConversationHandler.END
def gate2_open_confirm(bot, update):
    if update.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(update)
    update.message.reply_text("Подаем команду на GATE 2", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = "SIGNAL-" + str(chat_id)
    client.publish(gate2_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    #
    # log info
    write_com_log(chat_id, msg_send, "GATE 2")
    #
    return ConversationHandler.END
def garage_open_confirm(bot, update):
    if update.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(update)
    update.message.reply_text("Подаем команду на GARAGE", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = "SIGNAL-" + str(chat_id)
    client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    #
    # log info
    write_com_log(chat_id, msg_send, "GARAGE")
    #
    return ConversationHandler.END
def gate1_garage_open_confirm(bot, update):
    if update.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(update)
    update.message.reply_text("Подаем команду на GATE 1 и GARAGE", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = "SIGNAL-" + str(chat_id)
    client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    #
    # log info
    write_com_log(chat_id, msg_send, "GATE 1 and GARAGE")
    #
    return ConversationHandler.END

# Ctrls commands
def ctrls_ping(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    if update.message.text == KeyboardEnum.GATE_1.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду для проверки связи контроллера GATE 1...\n"
        update.message.reply_text(reply_msg)
        msg_send = "PING-" + str(chat_id)
        client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.GATE_2.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду для проверки связи контроллера GATE 2...\n"
        update.message.reply_text(reply_msg)
        msg_send = "PING-" + str(chat_id)
        client.publish(gate2_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.GARAGE.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду для проверки связи контроллера GARAGE...\n"
        update.message.reply_text(reply_msg)
        msg_send = "PING-" + str(chat_id)
        client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.ALL.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду для проверки связи всем контроллерам...\n"
        update.message.reply_text(reply_msg)
        msg_send = "PING-" + str(chat_id)
        client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
        client.publish(gate2_topic, payload=msg_send, qos=mqtt_qos, retain=False)
        client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)
    return WorkflowEnum.CTRLS_PING
def ctrls_restart(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    if update.message.text == KeyboardEnum.GATE_1.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду на перезагрузку контроллера GATE 1...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = "RESET"
        client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.GATE_2.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду на перезагрузку контроллера GATE 2...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = "RESET"
        client.publish(gate2_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.GARAGE.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду на перезагрузку контроллера GARAGE...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = "RESET"
        client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.ALL.clean():
        chat_id = get_chat_id(update)
        reply_msg = "Отправляю команду на перезагрузку всех контроллеров...\n"
        update.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = "RESET"
        client.publish(gate1_topic, payload=msg_send, qos=mqtt_qos, retain=False)
        client.publish(gate2_topic, payload=msg_send, qos=mqtt_qos, retain=False)
        client.publish(garage_topic, payload=msg_send, qos=mqtt_qos, retain=False)
    elif update.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)
    return ConversationHandler.END

# Start command
def start(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    message = "Приветствую тебя, мой капитан! =)\n"
    update.message.reply_text(message, reply_markup=keyboard_cmds())

### Handlers ###
# Gates command handler
gate_handler = ConversationHandler(
    entry_points=[CommandHandler('gates', gates_cmd)],
    states={
        WorkflowEnum.GATES_SUB_CMD:
            [RegexHandler("^(GATE 1|GATE 2|GARAGE|GATE 1 AND GARAGE)$", gates_sub_cmd),
             RegexHandler("^(CANCEL)$", cancel)],
        WorkflowEnum.GATE1_OPEN_CONFIRM:
            [RegexHandler("^(YES|NO)$", gate1_open_confirm)],
        WorkflowEnum.GATE2_OPEN_CONFIRM:
            [RegexHandler("^(YES|NO)$", gate2_open_confirm)],
        WorkflowEnum.GARAGE_OPEN_CONFIRM:
            [RegexHandler("^(YES|NO)$", garage_open_confirm)],
        WorkflowEnum.GATE1_GARAGE_OPEN_CONFIRM:
            [RegexHandler("^(YES|NO)$", gate1_garage_open_confirm)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
dispatcher.add_handler(gate_handler)

# Conrtollers command handler
ctrl_handler = ConversationHandler(
    entry_points=[CommandHandler('ctrls', ctrls_cmd)],
    states={
        WorkflowEnum.CTRLS_SUB_CMD:
            [RegexHandler("^(PING|RESTART)$", ctrls_sub_cmd),
             RegexHandler("^(CANCEL)$", cancel)],
        WorkflowEnum.CTRLS_PING:
            [RegexHandler("^(GATE 1|GATE 2|GARAGE|ALL)$", ctrls_ping),
             RegexHandler("^(CANCEL)$", cancel)],
        WorkflowEnum.CTRLS_RESTART:
            [RegexHandler("^(GATE 1|GATE 2|GARAGE|ALL)$", ctrls_restart),
             RegexHandler("^(CANCEL)$", cancel)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
dispatcher.add_handler(ctrl_handler)

start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

### END Handlers ###

# Start the bot
updater.start_polling()

# Show welcome message, update state and keyboard for commands
message = "KalachevoBot is running!\n"
for user_id in user_id_list:
    try:
        updater.bot.send_message(user_id, message, reply_markup=keyboard_cmds())
    except:
        continue


### Start MQTT ###
try:
    while True:
        client.loop_forever()
except KeyboardInterrupt:
    logging.info("MQTT exiting")
    client.disconnect()
    client.loop_stop()
### END MQTT ###



