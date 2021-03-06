import json
import logging
import socket
import struct
from enum import Enum, auto

import paho.mqtt.client as mqttclient
from telegram import KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters

# Logging
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

# Read configuration
with open("config.json") as config_file:
    config = json.load(config_file)

user_id_list = tuple(config["user_id_list"])

# NTP settings
# (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
ntp_delta = 3155673600
host = "pool.ntp.org"

REQUEST_KWARGS={
    'proxy_url': config["telegram_proxy_url"],
    # Optional, if you need authentication:
    'urllib3_proxy_kwargs': {
        'username': config["telegram_proxy_username"],
        'password': config["telegram_proxy_password"],
    }
}

if config["telegram_proxy"]:
    updater = Updater(token=config["bot_token"], request_kwargs=REQUEST_KWARGS, use_context=True)
else:
    updater = Updater(token=config["bot_token"], use_context=True)

dispatcher = updater.dispatcher
job_queue = updater.job_queue


# Write command to log
def write_com_log(user_id, command, controller):
    logging.info("User: " + str(user_id) + ", gave the command: " + command + " to controller: " + str(controller))


### MQTT ###

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
        global Connected  # Use global variable
        Connected = True  # Signal connection
    else:
        print("Connection failed")
    client.subscribe("street/#")

def on_message(client, userdata, message):
    logging.debug("MQTT topic: " + str(message.topic) + ", message: " + str(message.payload))
    m_decode = str(message.payload.decode("utf-8", "ignore"))
    if json.loads(m_decode)['command'] == "PONG" and message.topic == config["gate1_topic"]:
        t_message = "Контроллер GATE 1 на связи.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)
    elif json.loads(m_decode)['command'] == "PONG" and message.topic == config["gate2_topic"]:
        t_message = "Контроллер GATE 2 на связи.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)
    elif json.loads(m_decode)['command'] == "PONG" and message.topic == config["garage_topic"]:
        t_message = "Контроллер GARAGE на связи.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)
    elif json.loads(m_decode)['command'] == "OPEN" and message.topic == config["gate1_topic"]:
        t_message = "Gate 1: команда получена.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)
    elif json.loads(m_decode)['command'] == "OPEN" and message.topic == config["gate2_topic"]:
        t_message = "Gate 2: команда получена.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)
    elif json.loads(m_decode)['command'] == "OPEN" and message.topic == config["garage_topic"]:
        t_message = "Garage ворота: команда получена.\n"
        updater.bot.send_message(json.loads(m_decode)['userid'], t_message)


Connected = False  # global variable for the state of the connection
client = mqttclient.Client(config["mqtt_client_id"])  # create new instance
client.username_pw_set(config["mqtt_user"], password=config["mqtt_password"])  # set username and password
client.on_connect = on_connect  # attach function to callback
client.on_message = on_message  # attach function to callback

if config["mqtt_tls"]:
    client.tls_set("cacert.pem")
    client.connect(config["mqtt_broker"], port=config["port_ssl"], keepalive=60)  # connect to broker
else:
    client.connect(config["mqtt_broker"], port=config["port"], keepalive=60)  # connect to broker

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
    return val - ntp_delta

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
# def is_user_valid(update, context):
    # chat_id = get_chat_id(bot)
    chat_id = get_chat_id(bot)
    found = 0
    for user_id in user_id_list:
        if str(chat_id) == user_id:
            found = 1
            break
#    if str(chat_id) != user_id:
    if found != 1:
        bot.send_message(chat_id, text="Access denied for id: " + str(chat_id))
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
    bot.message.reply_text("Отмена...", reply_markup=keyboard_cmds())
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
    bot.message.reply_text(reply_msg, reply_markup=reply_mrk)

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
    bot.message.reply_text(reply_msg, reply_markup=reply_mrk)

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
# def gates_sub_cmd(update, context):
    # Command to GATE 1
    if bot.message.text == KeyboardEnum.GATE_1.clean():
        reply_msg = "Подтвердите действие...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE1_OPEN_CONFIRM
    elif bot.message.text == KeyboardEnum.GATE_2.clean():
        reply_msg = "Подтвердите действие...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE2_OPEN_CONFIRM
    elif bot.message.text == KeyboardEnum.GARAGE.clean():
        reply_msg = "Подтвердите действие...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GARAGE_OPEN_CONFIRM
    elif bot.message.text == KeyboardEnum.GATE_1_AND_GARAGE.clean():
        reply_msg = "Подтвердите действие...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_confirm())
        return WorkflowEnum.GATE1_GARAGE_OPEN_CONFIRM
    elif bot.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)

# Controllers SUB commands
def ctrls_sub_cmd(bot, update):
    pass
    # Command to CTL 1
    if bot.message.text == KeyboardEnum.PING.clean():
        reply_msg = "Выберете контроллер для проверки связи...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_ctrls())
        return WorkflowEnum.CTRLS_PING
    elif bot.message.text == KeyboardEnum.RESTART.clean():
        reply_msg = "Выберете контроллер для перезагрузки...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_ctrls())
        return WorkflowEnum.CTRLS_RESTART
    elif bot.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)

### CONFIRMATION ###

# Gates confirmation
def gate1_open_confirm(bot, update):
    if bot.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(bot)
    bot.message.reply_text("Подаем команду на GATE 1", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = {
        'command': "SIGNAL",
        'userid': str(chat_id)
    }
    client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    # log info
    write_com_log(chat_id, json.dumps(msg_send), "GATE 1")
    #
    return ConversationHandler.END
def gate2_open_confirm(bot, update):
    if bot.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(bot)
    bot.message.reply_text("Подаем команду на GATE 2", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = {
        'command': "SIGNAL",
        'userid': str(chat_id)
    }
    client.publish(config["gate2_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    #
    # log info
    write_com_log(chat_id, json.dumps(msg_send), "GATE 2")
    #
    return ConversationHandler.END
def garage_open_confirm(bot, update):
    if bot.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(bot)
    bot.message.reply_text("Подаем команду на GARAGE", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = {
        'command': "SIGNAL",
        'userid': str(chat_id)
    }
    client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    #
    # log info
    write_com_log(chat_id, json.dumps(msg_send), "GARAGE")
    #
    return ConversationHandler.END
def gate1_garage_open_confirm(bot, update):
    if bot.message.text == KeyboardEnum.NO.clean():
        return cancel(bot, update)
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    chat_id = get_chat_id(bot)
    bot.message.reply_text("Подаем команду на GATE 1 и GARAGE", reply_markup=keyboard_cmds())
    # MQTT string
    msg_send = {
        'command': "SIGNAL",
        'userid': str(chat_id)
    }
    client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    #
    # log info
    write_com_log(chat_id, json.dumps(msg_send), "GATE 1 and GARAGE")
    #
    return ConversationHandler.END

# Ctrls commands
def ctrls_ping(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    if bot.message.text == KeyboardEnum.GATE_1.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду для проверки связи контроллера GATE 1...\n"
        bot.message.reply_text(reply_msg)
        msg_send = {
            'command': "PING",
            'userid': str(chat_id)
        }
        client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.GATE_2.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду для проверки связи контроллера GATE 2...\n"
        bot.message.reply_text(reply_msg)
        msg_send = {
            'command': "PING",
            'userid': str(chat_id)
        }
        client.publish(config["gate2_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.GARAGE.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду для проверки связи контроллера GARAGE...\n"
        bot.message.reply_text(reply_msg)
        msg_send = {
            'command': "PING",
            'userid': str(chat_id)
        }
        client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.ALL.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду для проверки связи всем контроллерам...\n"
        bot.message.reply_text(reply_msg)
        msg_send = {
            'command': "PING",
            'userid': str(chat_id)
        }
        client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
        client.publish(config["gate2_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
        client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)
    return WorkflowEnum.CTRLS_PING
def ctrls_restart(bot, update):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    if bot.message.text == KeyboardEnum.GATE_1.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду на перезагрузку контроллера GATE 1...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = {
            'command': "RESET",
            'userid': str(chat_id)
        }
        client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.GATE_2.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду на перезагрузку контроллера GATE 2...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = {
            'command': "RESET",
            'userid': str(chat_id)
        }
        client.publish(config["gate2_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.GARAGE.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду на перезагрузку контроллера GARAGE...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = {
            'command': "RESET",
            'userid': str(chat_id)
        }
        client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.ALL.clean():
        chat_id = get_chat_id(bot)
        reply_msg = "Отправляю команду на перезагрузку всех контроллеров...\n"
        bot.message.reply_text(reply_msg, reply_markup=keyboard_cmds())
        msg_send = {
            'command': "RESET",
            'userid': str(chat_id)
        }
        client.publish(config["gate1_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
        client.publish(config["gate2_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
        client.publish(config["garage_topic"], payload=json.dumps(msg_send), qos=config["mqtt_qos"], retain=False)
    elif bot.message.text == KeyboardEnum.CANCEL.clean():
        return cancel(bot, update)
    return ConversationHandler.END

# Start command
def start(bot, update):
# def start(update, context):
    if not is_user_valid(bot, update):
        return cancel(bot, update)
    message = "Приветствую тебя, мой капитан! =)\n"
    bot.message.reply_text(message, reply_markup=keyboard_cmds())

### Handlers ###
# Gates command handler
gate_handler = ConversationHandler(
    entry_points=[CommandHandler('gates', gates_cmd)],
    # states={
    #     WorkflowEnum.GATES_SUB_CMD:
    #         [RegexHandler("^(GATE 1|GATE 2|GARAGE|GATE 1 AND GARAGE)$", gates_sub_cmd),
    #          RegexHandler("^(CANCEL)$", cancel)],
    #     WorkflowEnum.GATE1_OPEN_CONFIRM:
    #         [RegexHandler("^(YES|NO)$", gate1_open_confirm)],
    #     WorkflowEnum.GATE2_OPEN_CONFIRM:
    #         [RegexHandler("^(YES|NO)$", gate2_open_confirm)],
    #     WorkflowEnum.GARAGE_OPEN_CONFIRM:
    #         [RegexHandler("^(YES|NO)$", garage_open_confirm)],
    #     WorkflowEnum.GATE1_GARAGE_OPEN_CONFIRM:
    #         [RegexHandler("^(YES|NO)$", gate1_garage_open_confirm)]
    # },
    states={
        WorkflowEnum.GATES_SUB_CMD:
            [MessageHandler(Filters.regex('^(GATE 1|GATE 2|GARAGE|GATE 1 AND GARAGE)$'), gates_sub_cmd),
             MessageHandler(Filters.regex('^(CANCEL)$'), cancel)],
        WorkflowEnum.GATE1_OPEN_CONFIRM:
            [MessageHandler(Filters.regex('^(YES|NO)$'), gate1_open_confirm)],
        WorkflowEnum.GATE2_OPEN_CONFIRM:
            [MessageHandler(Filters.regex('^(YES|NO)$'), gate2_open_confirm)],
        WorkflowEnum.GARAGE_OPEN_CONFIRM:
            [MessageHandler(Filters.regex('^(YES|NO)$'), garage_open_confirm)],
        WorkflowEnum.GATE1_GARAGE_OPEN_CONFIRM:
            [MessageHandler(Filters.regex('^(YES|NO)$'), gate1_garage_open_confirm)]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
dispatcher.add_handler(gate_handler)

# Conrtollers command handler
ctrl_handler = ConversationHandler(
    entry_points=[CommandHandler('ctrls', ctrls_cmd)],
    states={
        WorkflowEnum.CTRLS_SUB_CMD:
            [MessageHandler(Filters.regex('^(PING|RESTART)$'), ctrls_sub_cmd),
             MessageHandler(Filters.regex('^(CANCEL)$'), cancel)],
        WorkflowEnum.CTRLS_PING:
            [MessageHandler(Filters.regex('^(GATE 1|GATE 2|GARAGE|ALL)$'), ctrls_ping),
             MessageHandler(Filters.regex('^(CANCEL)$'), cancel)],
        WorkflowEnum.CTRLS_RESTART:
            [MessageHandler(Filters.regex('^(GATE 1|GATE 2|GARAGE|ALL)$'), ctrls_restart),
             MessageHandler(Filters.regex('^(CANCEL)$'), cancel)]
    },
    # states={
    #     WorkflowEnum.CTRLS_SUB_CMD:
    #         [RegexHandler("^(PING|RESTART)$", ctrls_sub_cmd),
    #          RegexHandler("^(CANCEL)$", cancel)],
    #     WorkflowEnum.CTRLS_PING:
    #         [RegexHandler("^(GATE 1|GATE 2|GARAGE|ALL)$", ctrls_ping),
    #          RegexHandler("^(CANCEL)$", cancel)],
    #     WorkflowEnum.CTRLS_RESTART:
    #         [RegexHandler("^(GATE 1|GATE 2|GARAGE|ALL)$", ctrls_restart),
    #          RegexHandler("^(CANCEL)$", cancel)]
    # },
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



