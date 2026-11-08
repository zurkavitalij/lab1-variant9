#!/bin/bash
# Запуск gunicorn в фоне, проверка клиентом и остановка сервера.
# Скрипт возвращает код завершения client.py, поэтому при ошибке
# проверка в GitHub Actions будет провалена (раздел 2.11 МУ).
gunicorn --bind 127.0.0.1:5000 wsgi:app & APP_PID=$!
sleep 5
echo start client
python3 client.py
APP_CODE=$?
sleep 1
echo $APP_PID
kill -TERM $APP_PID
echo app code $APP_CODE
exit $APP_CODE
