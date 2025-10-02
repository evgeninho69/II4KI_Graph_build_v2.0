from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .units import mm_to_px


@dataclass(frozen=True)
class PageFormat:
    name: str  # 'A4' | 'A3'
    orientation: str = 'portrait'  # only portrait for now
    width_mm: float = 210.0
    height_mm: float = 297.0
    margin_left_mm: float = 20.0
    margin_right_mm: float = 20.0
    margin_top_mm: float = 10.0
    margin_bottom_mm: float = 10.0

    @property
    def workarea_width_mm(self) -> float:
        return max(0.0, self.width_mm - self.margin_left_mm - self.margin_right_mm)

    @property
    def workarea_height_mm(self) -> float:
        return max(0.0, self.height_mm - self.margin_top_mm - self.margin_bottom_mm)


def _scale_denominator_for_bbox(content_width_m: float, content_height_m: float, work_w_mm: float, work_h_mm: float) -> float:
    # 1:N, где 1 мм на листе = N мм на местности
    content_w_mm = max(1e-9, content_width_m * 1000.0)
    content_h_mm = max(1e-9, content_height_m * 1000.0)
    n_w = content_w_mm / max(1e-9, work_w_mm)
    n_h = content_h_mm / max(1e-9, work_h_mm)
    return max(n_w, n_h)


def choose_format_and_scale(content_bbox: Tuple[float, float, float, float], allowed_scales: list[int] | None = None, min_font_pt: int = 7, dpi: int = 96) -> Tuple[PageFormat, int]:
    """
    Возвращает (формат, масштаб N для подписи "1:N").
    Правило: пробуем A4-портрет; если N_A4 > 1000 — берём A3-портрет.
    Минимальный размер шрифта обеспечивается на стороне рендера (px>=7pt).
    """
    min_x, min_y, max_x, max_y = content_bbox
    content_w_m = max(1e-9, max_x - min_x)
    content_h_m = max(1e-9, max_y - min_y)

    a4 = PageFormat(name='A4', width_mm=210.0, height_mm=297.0)
    a3 = PageFormat(name='A3', width_mm=297.0, height_mm=420.0)

    allowed = sorted(allowed_scales or [500, 1000, 2000, 5000])

    # Функция подбора ближайшего допустимого масштаба для данного формата
    def pick_for(fmt: PageFormat) -> int | None:
        need_n = _scale_denominator_for_bbox(content_w_m, content_h_m, fmt.workarea_width_mm, fmt.workarea_height_mm)
        for n in allowed:
            if n >= need_n:
                return int(n)
        return int(allowed[-1]) if allowed else int(round(need_n))

    n_a4 = pick_for(a4)
    if n_a4 is not None:
        return a4, n_a4
    n_a3 = pick_for(a3)
    return a3, n_a3 if n_a3 is not None else int(round(_scale_denominator_for_bbox(content_w_m, content_h_m, a3.workarea_width_mm, a3.workarea_height_mm)))


