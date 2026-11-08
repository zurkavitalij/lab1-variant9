"""Клиент для проверки запущенного сервера (вызывается из st.sh).

Отправляет запросы к страницам и JSON API, при любой ошибке
завершается с кодом 1 — тогда проверка в CI считается проваленной.
"""
import base64
import os
import sys

import requests

BASE_URL = os.environ.get("APP_URL", "http://localhost:5000")


def check_page(path):
    """GET-запрос к странице; код ответа должен быть 200."""
    r = requests.get(BASE_URL + path, timeout=30)
    print(path, r.status_code)
    if r.status_code != 200:
        sys.exit(1)
    return r


try:
    check_page("/")
    check_page("/hello")
    print(check_page("/data_to").text)
    print(check_page("/apixml").text)

    # кодируем тестовую картинку в base64 и отправляем в JSON API
    path = os.path.join(os.path.dirname(__file__), "static", "samples",
                        "chelsea.jpg")
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read())
    jsondata = {"imagebin": b64.decode("utf-8"), "r": 120, "g": 100, "b": 40}
    res = requests.post(BASE_URL + "/api/intensity", json=jsondata,
                        timeout=60)
    print("/api/intensity", res.status_code)
    if not res.ok:
        sys.exit(1)
    body = res.json()
    for src, new in zip(body["stats_src"], body["stats_new"]):
        print(f'{src["channel"]}: среднее {src["mean"]} -> {new["mean"]}')
except requests.RequestException as exc:
    print("Ошибка запроса:", exc)
    sys.exit(1)
