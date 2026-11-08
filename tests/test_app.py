"""Unit- и функциональные тесты приложения (запуск: pytest)."""
import base64
import io
import os
import sys

import numpy as np
import pytest
from PIL import Image

# добавляем каталог flaskapp в путь поиска модулей
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "flaskapp")
sys.path.insert(0, os.path.abspath(APP_DIR))

import captcha  # noqa: E402
import image_tools  # noqa: E402
from some_app import app  # noqa: E402


def make_png(color=(100, 150, 200), size=(40, 30), mode="RGB"):
    """Создаёт однотонное тестовое изображение и возвращает его байты."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as c:
        yield c


# ---------------- обработка изображений ----------------
def test_identity_factors_keep_image():
    arr = np.random.randint(0, 256, (10, 12, 3), dtype=np.uint8)
    assert np.array_equal(image_tools.change_intensity(arr, (1, 1, 1)), arr)


def test_change_one_channel():
    arr = np.full((2, 2, 3), 100, dtype=np.uint8)
    out = image_tools.change_intensity(arr, (1.5, 1.0, 0.0))
    assert out[0, 0].tolist() == [150, 100, 0]


def test_change_several_channels_and_clip():
    arr = np.full((2, 2, 3), 200, dtype=np.uint8)
    out = image_tools.change_intensity(arr, (2.0, 0.5, 3.0))
    # 400 и 600 должны ограничиться значением 255
    assert out[1, 1].tolist() == [255, 100, 255]
    assert out.dtype == np.uint8


def test_negative_factor_rejected():
    arr = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        image_tools.change_intensity(arr, (-1, 1, 1))


def test_alpha_channel_preserved():
    img = image_tools.load_image(make_png((10, 20, 30, 77), mode="RGBA"))
    out = image_tools.process_image(img, (200, 100, 0))
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0)) == (20, 20, 0, 77)


def test_histogram_counts_all_pixels():
    img = image_tools.load_image(make_png(size=(8, 5)))
    hist = image_tools.channel_histograms(img)
    assert hist.shape == (3, 256)
    assert hist.sum(axis=1).tolist() == [40, 40, 40]
    assert hist[0, 100] == 40 and hist[2, 200] == 40


def test_histogram_figure_is_png():
    img = image_tools.load_image(make_png())
    png = image_tools.histogram_figure(img, img)
    assert png.startswith(b"\x89PNG")


def test_load_image_rejects_garbage():
    with pytest.raises(ValueError):
        image_tools.load_image(b"not an image")


# ---------------- капча ----------------
def test_captcha_verify_once():
    sess = {}
    code = captcha.new_code(sess, "key")
    assert captcha.verify(sess, "key", code.lower())
    # повторное использование того же кода запрещено
    assert not captcha.verify(sess, "key", code)


def test_captcha_wrong_code():
    sess = {}
    captcha.new_code(sess, "key")
    assert not captcha.verify(sess, "key", "WRONG")


# ---------------- веб-приложение ----------------
def test_pages_available(client):
    for url in ("/", "/hello", "/data_to", "/apixml", "/health"):
        assert client.get(url).status_code == 200
    resp = client.get("/captcha.png")
    assert resp.mimetype == "image/png"


def test_form_with_valid_captcha(client):
    # кладём известный код капчи в сессию тестового клиента
    with client.session_transaction() as sess:
        code = captcha.new_code(sess, app.config["SECRET_KEY"])
    data = {"upload": (io.BytesIO(make_png()), "test.png"),
            "red": "50", "green": "100", "blue": "0", "captcha": code}
    resp = client.post("/", data=data, content_type="multipart/form-data")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Графики распределения цветов" in html
    assert "data:image/png;base64," in html


def test_form_with_wrong_captcha(client):
    with client.session_transaction() as sess:
        captcha.new_code(sess, app.config["SECRET_KEY"])
    data = {"upload": (io.BytesIO(make_png()), "test.png"),
            "red": "50", "green": "100", "blue": "0", "captcha": "AAAAA"}
    resp = client.post("/", data=data, content_type="multipart/form-data")
    html = resp.get_data(as_text=True)
    assert "введён неверно" in html
    assert "Графики распределения цветов" not in html


def test_api_intensity(client):
    b64 = base64.b64encode(make_png((100, 100, 100))).decode()
    resp = client.post("/api/intensity",
                       json={"imagebin": b64, "r": 200, "g": 100, "b": 50})
    assert resp.status_code == 200
    body = resp.get_json()
    out = Image.open(io.BytesIO(base64.b64decode(body["image"])))
    assert out.getpixel((0, 0)) == (200, 100, 50)
    assert body["stats_new"][0]["mean"] == 200.0


def test_api_bad_requests(client):
    assert client.post("/api/intensity", json={}).status_code == 400
    assert client.post("/api/intensity",
                       json={"imagebin": "@@@"}).status_code == 400
    b64 = base64.b64encode(make_png()).decode()
    assert client.post("/api/intensity",
                       json={"imagebin": b64, "r": 500}).status_code == 400
