FROM python:3

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /opt/bot-app
ADD bot-app /opt/bot-app

CMD [ "python", "./kalachevobot.py" ]
