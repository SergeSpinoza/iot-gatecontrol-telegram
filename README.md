# iot-gatecontrol-telegram

This repository contains 2 directories:
- esp8266 - code on MicroPython for micro controllers NodeMCU (esp8266)
- telegrambot - code on Python. It's telegram bot for control micro controllers via MQTT protocol.

Configure MQTT connection in main.py (section CONFIG) and in kalachevobot.py (section # MQTT Settings and # Telegram settings)

You also need to add to root 'telegrambot' directory CA certificate (on my code it names cacert.pem), if you want to use SSL connection to MQTT server.

