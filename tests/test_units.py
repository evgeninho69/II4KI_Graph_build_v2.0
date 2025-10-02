from mp_graphics.core.units import mm_to_px, DEFAULT_DPI


def test_mm_to_px_default_dpi():
    # 25.4 мм дают ~96 px при 96 DPI (учтём плавающую арифметику)
    assert abs(mm_to_px(25.4, DEFAULT_DPI) - 96.0) < 1e-9


def test_mm_to_px_arbitrary():
    # 0.2 мм при 96 DPI ≈ 0.7559 px
    val = mm_to_px(0.2, 96)
    assert abs(val - 0.7559) < 1e-3


