# ЛР № 1 «Разработка веб-приложения на Python». Вариант 9

Веб-приложение на Flask изменяет интенсивность одной или нескольких
цветовых карт изображения (R, G, B) и строит графики распределения
цветов исходной и новой картинки. Форма защищена капчей.

## Запуск локально

```bash
pipenv sync
cd flaskapp
pipenv run gunicorn --bind 127.0.0.1:5000 wsgi:app
# открыть http://127.0.0.1:5000
```

## Тесты

```bash
pipenv run python -m pytest -v tests     # unit- и функциональные тесты
cd flaskapp && pipenv run ./st.sh         # запуск сервера + client.py
```

## Адреса

| Адрес | Назначение |
|---|---|
| `/` | форма варианта 9 и результат |
| `/captcha.png` | картинка капчи |
| `/api/intensity` | JSON API (POST: imagebin, r, g, b) |
| `/hello`, `/data_to`, `/apixml` | примеры из методических указаний |
| `/health` | проверка работоспособности для render.com |

## Деплой на render.com

Build command: `python -m pip install pipenv && pipenv sync`
Start command: `pipenv run gunicorn wsgi:app --chdir flaskapp --bind 0.0.0.0:$PORT --workers 1 --timeout 120`
Переменные окружения: `PYTHON_VERSION=3.11.9`, `SECRET_KEY=<случайная строка>`.
