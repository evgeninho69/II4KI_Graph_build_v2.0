DEFAULT_DPI: int = 96


def mm_to_px(mm: float, dpi: int = DEFAULT_DPI) -> float:
    """Конвертирует миллиметры в пиксели для заданного DPI.

    Формула: px = mm * dpi / 25.4
    """
    return float(mm) * float(dpi) / 25.4


