"""Лабораторная работа № 1 «Разработка веб-приложения на Python».

Вариант 9: веб-приложение изменяет интенсивность любой цветовой карты
изображения (R, G, B) или сразу нескольких и выводит графики
распределения цветов исходной и новой картинки.

Кроме основного задания, в файле есть примеры из методических указаний:
/hello, /data_to (шаблоны Jinja2), /apixml (XML + XSLT).
"""
import base64
import binascii
import json
import os
import secrets

import lxml.etree as ET
from flask import (Flask, Response, jsonify, render_template, request,
                   session)
from flask_bootstrap import Bootstrap5
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from werkzeug.exceptions import RequestEntityTooLarge
from wtforms import IntegerRangeField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, ValidationError

import captcha
import image_tools

# каталог приложения: пути к static и templates не зависят от того,
# из какой папки запущен сервер (PyCharm, gunicorn --chdir, pytest)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# Секретный ключ подписывает cookie сессии и CSRF-токены форм.
# На сервере он задаётся переменной окружения SECRET_KEY; если её нет,
# ключ генерируется случайно при запуске (как советуют методические указания)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
# ограничение размера загружаемого файла (по умолчанию 10 МБ)
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024
# Bootstrap отдаётся с нашего сервера, а не из CDN
app.config["BOOTSTRAP_SERVE_LOCAL"] = True
# капчу можно отключить только для автоматических тестов
app.config["CAPTCHA_ENABLED"] = os.environ.get("CAPTCHA_ENABLED", "1") != "0"

bootstrap = Bootstrap5(app)
# функция zip нужна в шаблоне для вывода статистики «до → после»
app.jinja_env.globals["zip"] = zip

ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif",
                      "tiff"]


# ---------------------------------------------------------------------------
# Примеры из методических указаний (разделы 2.5–2.6, 2.11)
# ---------------------------------------------------------------------------
@app.route("/hello")
def hello():
    """Простейшая страница Hello World (раздел 2.5)."""
    return " <html><head></head> <body> Hello World! </body></html>"


@app.route("/data_to")
def data_to():
    """Передача данных в шаблон Jinja2 (раздел 2.6)."""
    some_pars = {"user": "Ivan", "color": "red"}
    some_str = "Hello my dear friends!"
    some_value = 10
    return render_template("simple.html", some_str=some_str,
                           some_value=some_value, some_pars=some_pars)


@app.route("/apixml", methods=["GET", "POST"])
def apixml():
    """Преобразование XML-документа в HTML шаблоном XSLT (раздел 2.11)."""
    dom = ET.parse(os.path.join(BASE_DIR, "static", "xml", "file.xml"))
    xslt = ET.parse(os.path.join(BASE_DIR, "static", "xml", "file.xslt"))
    transform = ET.XSLT(xslt)
    newhtml = transform(dom)
    strfile = ET.tostring(newhtml, encoding="utf-8")
    return Response(strfile, mimetype="text/html")


# ---------------------------------------------------------------------------
# Вариант 9: изменение интенсивности цветовых карт
# ---------------------------------------------------------------------------
def captcha_check(form, field):
    """Валидатор WTForms: сверяет введённый код с кодом из сессии."""
    if not app.config["CAPTCHA_ENABLED"]:
        return
    if not captcha.verify(session, app.config["SECRET_KEY"], field.data):
        raise ValidationError("Код с картинки введён неверно. "
                              "Введите новый код.")


def percent_field(label):
    """Ползунок интенсивности канала: от 0 до 300 %, по умолчанию 100 %."""
    return IntegerRangeField(
        label, default=100,
        validators=[NumberRange(image_tools.MIN_PERCENT,
                                image_tools.MAX_PERCENT,
                                "Допустимы значения от 0 до 300 %")],
        render_kw={"min": image_tools.MIN_PERCENT,
                   "max": image_tools.MAX_PERCENT, "step": 1})


class IntensityForm(FlaskForm):
    """Форма загрузки изображения и выбора интенсивности каналов."""
    upload = FileField("Изображение", validators=[
        FileRequired("Выберите файл изображения"),
        FileAllowed(ALLOWED_EXTENSIONS, "Можно загружать только изображения")])
    red = percent_field("Красный канал (R), %")
    green = percent_field("Зелёный канал (G), %")
    blue = percent_field("Синий канал (B), %")
    captcha = StringField("Код с картинки", validators=[
        DataRequired("Введите код с картинки"), captcha_check],
        render_kw={"autocomplete": "off", "maxlength": captcha.LENGTH})
    submit = SubmitField("Применить")


@app.route("/", methods=["GET", "POST"])
def index():
    """Главная страница: форма, результат обработки и графики."""
    form = IntensityForm()
    result = None
    error = None
    if form.validate_on_submit():
        percents = (form.red.data, form.green.data, form.blue.data)
        try:
            original = image_tools.load_image(form.upload.data.read())
            processed = image_tools.process_image(original, percents)
            result = {
                "percents": percents,
                "size": original.size,
                "original": image_tools.to_data_uri(
                    image_tools.image_to_bytes(original)),
                "processed": image_tools.to_data_uri(
                    image_tools.image_to_bytes(processed)),
                "histogram": image_tools.to_data_uri(
                    image_tools.histogram_figure(original, processed)),
                "stats_src": image_tools.channel_stats(original),
                "stats_new": image_tools.channel_stats(processed),
            }
        except ValueError as exc:
            error = str(exc)
    elif request.method == "POST":
        error = "Проверьте данные формы."
    # поле капчи очищаем: после каждой отправки нужен новый код
    form.captcha.data = ""
    return render_template("index.html", form=form, result=result,
                           error=error)


@app.route("/captcha.png")
def captcha_image():
    """Генерирует новую картинку капчи и сохраняет код в сессии."""
    code = captcha.new_code(session, app.config["SECRET_KEY"])
    resp = Response(captcha.render(code), mimetype="image/png")
    # запрещаем кеширование: при каждом запросе должна быть новая картинка
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.route("/api/intensity", methods=["POST"])
def api_intensity():
    """JSON API (по аналогии с /apinet из раздела 2.10).

    Запрос: {"imagebin": "<base64>", "r": 100, "g": 50, "b": 150}
    Ответ: {"image": "<base64 PNG>", "stats_src": [...], "stats_new": [...]}
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "imagebin" not in data:
        return jsonify(error="Ожидается JSON с полем imagebin"), 400
    try:
        percents = tuple(int(data.get(key, 100)) for key in ("r", "g", "b"))
    except (TypeError, ValueError):
        return jsonify(error="Поля r, g, b должны быть целыми числами"), 400
    if any(not image_tools.MIN_PERCENT <= p <= image_tools.MAX_PERCENT
           for p in percents):
        return jsonify(error="Интенсивность должна быть от 0 до 300 %"), 400
    try:
        raw = base64.b64decode(data["imagebin"].encode("utf-8"),
                               validate=True)
        original = image_tools.load_image(raw)
    except (binascii.Error, ValueError, AttributeError):
        return jsonify(error="Поле imagebin не содержит изображения"), 400
    processed = image_tools.process_image(original, percents)
    body = {
        "percents": {"r": percents[0], "g": percents[1], "b": percents[2]},
        "size": list(original.size),
        "stats_src": image_tools.channel_stats(original),
        "stats_new": image_tools.channel_stats(processed),
        "image": base64.b64encode(
            image_tools.image_to_bytes(processed)).decode("ascii"),
    }
    return Response(json.dumps(body, ensure_ascii=False), status=200,
                    mimetype="application/json")


@app.route("/health")
def health():
    """Проверка работоспособности для render.com (Health Check Path)."""
    return jsonify(status="ok")


@app.errorhandler(RequestEntityTooLarge)
def too_large(_exc):
    """Понятное сообщение при превышении размера файла."""
    limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    if request.path.startswith("/api/"):
        return jsonify(error=f"Файл больше {limit} МБ"), 413
    form = IntensityForm(formdata=None)
    return render_template("index.html", form=form, result=None,
                           error=f"Файл слишком большой (больше {limit} МБ)"
                           ), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
