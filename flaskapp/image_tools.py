"""Обработка изображений для варианта 9.

Модуль изменяет интенсивность цветовых карт (каналов R, G, B)
изображения и строит графики распределения цветов (гистограммы).
Все функции работают с массивами numpy и не обращаются к диску,
поэтому их удобно покрывать unit-тестами.
"""
import base64
import io

import matplotlib

# Backend Agg рисует графики в память без графического окна,
# это обязательно для работы на сервере (GitHub Actions, render.com)
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

# Названия и цвета каналов для подписей и графиков
CHANNELS = ("R", "G", "B")
CHANNEL_COLORS = ("#d62728", "#2ca02c", "#1f77b4")
CHANNEL_NAMES = ("Красный (R)", "Зелёный (G)", "Синий (B)")

# Допустимый диапазон коэффициента интенсивности, %
MIN_PERCENT = 0
MAX_PERCENT = 300

# Максимальный размер стороны изображения при обработке, пикселей.
# Большие фотографии уменьшаются, чтобы не превышать лимит памяти
# бесплатного тарифа PaaS (512 МБ на render.com)
MAX_SIDE = 1600


def load_image(data):
    """Читает изображение из байтов и приводит его к RGB или RGBA.

    :param data: содержимое файла изображения (bytes)
    :return: объект PIL.Image в режиме RGB или RGBA
    :raises ValueError: если данные не являются изображением
    """
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # PIL выбрасывает разные типы исключений
        raise ValueError("Файл не является изображением") from exc
    # учитываем поворот фотографии из EXIF (снимки с телефона)
    image = ImageOps.exif_transpose(image)
    # палитровые, ч/б и CMYK изображения переводим в RGB(A)
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")
    # уменьшаем слишком большие изображения с сохранением пропорций
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return image


def change_intensity(rgb, factors):
    """Изменяет интенсивность цветовых карт изображения.

    Каждый канал умножается на свой коэффициент:
    I'(x, y, c) = min(255, I(x, y, c) * k_c).
    Коэффициент 1.0 оставляет канал без изменений, 0.0 полностью
    убирает цветовую карту, значения больше 1.0 усиливают её.

    :param rgb: массив numpy формы (H, W, 3) с типом uint8
    :param factors: последовательность из трёх коэффициентов (kR, kG, kB)
    :return: новый массив (H, W, 3) uint8
    """
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Ожидается массив формы (H, W, 3)")
    k = np.asarray(factors, dtype=np.float32)
    if k.shape != (3,):
        raise ValueError("Нужно задать ровно три коэффициента")
    if np.any(k < 0):
        raise ValueError("Коэффициенты не могут быть отрицательными")
    # broadcasting: вектор (3,) умножается на каждую точку (H, W, 3)
    result = rgb.astype(np.float32) * k[np.newaxis, np.newaxis, :]
    # округляем и ограничиваем диапазон 0..255, чтобы не было переполнения
    return np.clip(np.rint(result), 0, 255).astype(np.uint8)


def process_image(image, percents):
    """Применяет изменение интенсивности к изображению PIL.

    :param image: PIL.Image в режиме RGB или RGBA
    :param percents: интенсивность каналов в процентах (R, G, B)
    :return: новое изображение PIL того же режима
    """
    factors = [p / 100.0 for p in percents]
    arr = np.array(image)
    new_rgb = change_intensity(arr[:, :, :3], factors)
    if image.mode == "RGBA":
        # прозрачность (альфа-канал) переносим без изменений
        new_arr = np.dstack([new_rgb, arr[:, :, 3]])
        return Image.fromarray(new_arr, mode="RGBA")
    return Image.fromarray(new_rgb, mode="RGB")


def channel_histograms(image):
    """Считает гистограммы распределения значений каналов R, G, B.

    :param image: PIL.Image (RGB или RGBA)
    :return: массив (3, 256): число пикселей с каждым значением 0..255
    """
    arr = np.array(image.convert("RGB"))
    return np.array([
        np.bincount(arr[:, :, c].ravel(), minlength=256)
        for c in range(3)
    ])


def channel_stats(image):
    """Возвращает среднее и стандартное отклонение по каждому каналу."""
    arr = np.array(image.convert("RGB"), dtype=np.float64)
    stats = []
    for c, name in enumerate(CHANNEL_NAMES):
        values = arr[:, :, c]
        stats.append({
            "channel": name,
            "mean": round(float(values.mean()), 2),
            "std": round(float(values.std()), 2),
            "min": int(values.min()),
            "max": int(values.max()),
        })
    return stats


def histogram_figure(original, processed):
    """Строит графики распределения цветов исходной и новой картинки.

    Слева — гистограммы каналов исходного изображения, справа —
    полученного. Масштаб оси Y общий, чтобы графики было удобно сравнивать.

    :return: PNG-изображение графика (bytes)
    """
    hist_src = channel_histograms(original)
    hist_new = channel_histograms(processed)
    levels = np.arange(256)
    # Масштаб оси Y считаем без крайних значений 0 и 255: при сильном
    # усилении канала много пикселей «упирается» в 255 (насыщение),
    # и такой пик сделал бы остальную часть графика плоской.
    inner_max = max(hist_src[:, 1:255].max(), hist_new[:, 1:255].max(), 1)
    y_max = inner_max * 1.15
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True,
                             constrained_layout=True)
    titles = ("Исходное изображение", "Новое изображение")
    for ax, hist, title in zip(axes, (hist_src, hist_new), titles):
        for c in range(3):
            ax.plot(levels, hist[c], color=CHANNEL_COLORS[c], linewidth=1.3,
                    label=CHANNEL_NAMES[c])
            ax.fill_between(levels, hist[c], color=CHANNEL_COLORS[c],
                            alpha=0.15)
        # подписываем число пикселей в крайних значениях, если пик обрезан
        clipped = [f"{CHANNELS[c]}: {hist[c, 0]} / {hist[c, 255]}"
                   for c in range(3)
                   if max(hist[c, 0], hist[c, 255]) > y_max]
        if clipped:
            ax.text(0.5, 0.97, "Пикселей со значением 0 / 255:\n"
                    + ", ".join(clipped), transform=ax.transAxes,
                    ha="center", va="top", fontsize=8,
                    bbox={"boxstyle": "round", "fc": "white", "ec": "0.7"})
        ax.set_title(title)
        ax.set_xlim(0, 255)
        ax.set_ylim(0, y_max)
        ax.set_xlabel("Значение интенсивности (0–255)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Количество пикселей")
    axes[0].legend(loc="upper right")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    # обязательно закрываем фигуру, иначе память сервера будет расти
    plt.close(fig)
    return buf.getvalue()


def image_to_bytes(image, fmt="PNG"):
    """Сохраняет изображение PIL в байты указанного формата."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def to_data_uri(data, mime="image/png"):
    """Кодирует байты в data URI для вставки в тег <img>.

    Изображения не сохраняются в папку static, поэтому файлы
    пользователей не накапливаются на сервере.
    """
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
