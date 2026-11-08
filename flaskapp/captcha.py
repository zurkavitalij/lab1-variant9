"""Собственная графическая капча для проверки «на робота».

Сервер генерирует случайный код, сохраняет его хеш в сессии
пользователя (подписанная cookie Flask) и отдаёт картинку с искажённым
текстом. При отправке формы введённый код сравнивается с хешем.
Капча одноразовая: после проверки код удаляется из сессии.
Внешние сервисы и ключи (как у Google reCAPTCHA) не нужны.
"""
import hashlib
import hmac
import io
import secrets
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Символы без похожих пар (0/O, 1/I/l), чтобы человеку было проще читать
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 5
# Время жизни кода капчи, секунд
TTL = 600
SESSION_KEY = "captcha"
WIDTH, HEIGHT = 180, 64

# Пути к шрифтам: DejaVu есть в большинстве дистрибутивов Linux
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)


def _font(size):
    """Возвращает TrueType-шрифт, при его отсутствии — встроенный шрифт PIL."""
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _hash(code, secret):
    """HMAC-SHA256 от кода: в сессии не хранится сам ответ."""
    return hmac.new(secret.encode(), code.upper().encode(),
                    hashlib.sha256).hexdigest()


def new_code(session, secret):
    """Создаёт новый код капчи и запоминает его хеш в сессии."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    session[SESSION_KEY] = {"h": _hash(code, secret), "t": int(time.time())}
    return code


def verify(session, secret, answer):
    """Проверяет ответ пользователя. Код можно использовать один раз."""
    data = session.pop(SESSION_KEY, None)
    if not data or not answer:
        return False
    if time.time() - data.get("t", 0) > TTL:
        return False
    return hmac.compare_digest(data.get("h", ""),
                               _hash(answer.strip(), secret))


def render(code):
    """Рисует PNG-картинку капчи с шумом и искажениями."""
    rnd = secrets.SystemRandom()
    image = Image.new("RGB", (WIDTH, HEIGHT), (245, 245, 240))
    draw = ImageDraw.Draw(image)
    # фоновый шум: случайные точки
    for _ in range(600):
        xy = (rnd.randrange(WIDTH), rnd.randrange(HEIGHT))
        draw.point(xy, fill=tuple(rnd.randrange(120, 220) for _ in range(3)))
    # каждый символ рисуем на отдельном слое и поворачиваем
    step = WIDTH // (LENGTH + 1)
    for i, char in enumerate(code):
        layer = Image.new("RGBA", (48, 56), (0, 0, 0, 0))
        color = tuple(rnd.randrange(20, 110) for _ in range(3)) + (255,)
        ImageDraw.Draw(layer).text((6, 4), char, font=_font(38), fill=color)
        layer = layer.rotate(rnd.uniform(-28, 28), resample=Image.BICUBIC,
                             expand=False)
        x = 10 + i * step + rnd.randrange(-3, 4)
        y = rnd.randrange(-2, 10)
        image.paste(layer, (x, y), layer)
    # перечёркивающие линии мешают распознаванию простыми OCR
    for _ in range(4):
        points = [(rnd.randrange(WIDTH), rnd.randrange(HEIGHT))
                  for _ in range(2)]
        draw.line(points, fill=tuple(rnd.randrange(60, 160)
                                     for _ in range(3)), width=2)
    image = image.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
