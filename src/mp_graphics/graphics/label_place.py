from __future__ import annotations

from typing import List, Tuple, Optional
import math

from ..core.units import mm_to_px


def _segments_of_polyline(polyline: List[Tuple[float, float]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    segs = []
    for i in range(len(polyline) - 1):
        segs.append((polyline[i], polyline[i + 1]))
    return segs


def _ccw(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> bool:
    return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)


def _intersect(a1: Tuple[float, float], a2: Tuple[float, float], b1: Tuple[float, float], b2: Tuple[float, float]) -> bool:
    (x1, y1), (x2, y2) = a1, a2
    (x3, y3), (x4, y4) = b1, b2
    return _ccw(x1, y1, x3, y3, x4, y4) != _ccw(x2, y2, x3, y3, x4, y4) and _ccw(x1, y1, x2, y2, x3, y3) != _ccw(x1, y1, x2, y2, x4, y4)


def _line_intersects_polylines(p1: Tuple[float, float], p2: Tuple[float, float], polylines: List[List[Tuple[float, float]]]) -> bool:
    for poly in polylines:
        for s1, s2 in _segments_of_polyline(poly):
            if _intersect(p1, p2, s1, s2):
                return True
    return False


def place_label(anchor: Tuple[float, float], text: str, avoid_polylines: List[List[Tuple[float, float]]], *, dpi: int, font_size_px: int, min_font_pt: int = 7, prefer_center: bool = False) -> Tuple[float, float, Optional[str]]:
    """
    Возвращает (x_text, y_text, leader_line_svg|None).
    
    Если prefer_center=True (для подписей участков), сначала пробуем разместить точно в центре без выноски.
    Выноска создается только если центральное размещение пересекает линии или другие подписи.
    
    Если prefer_center=False (для подписей квартала), подбираем из 4 квадрантов со сдвигом 2 мм.
    """
    ax, ay = anchor
    
    # Для подписей участков - пробуем сначала разместить точно в центре
    if prefer_center:
        # Проверяем, не пересекает ли центральное размещение линии
        if not _line_intersects_polylines((ax, ay), (ax, ay), avoid_polylines):
            return ax, ay, None
    
    # Если центр занят или prefer_center=False, используем квадранты со сдвигом
    dx_mm, dy_mm = 2.0, 2.0
    dx = mm_to_px(dx_mm, dpi)
    dy = mm_to_px(dy_mm, dpi)
    min_leader_mm = 1.5
    min_leader_px = mm_to_px(min_leader_mm, dpi)

    candidates = [
        (ax + dx, ay - dy),  # вправо-вверх
        (ax - dx, ay - dy),  # влево-вверх
        (ax - dx, ay + dy),  # влево-вниз
        (ax + dx, ay + dy),  # вправо-вниз
    ]

    for cx, cy in candidates:
        if not _line_intersects_polylines((ax, ay), (cx, cy), avoid_polylines):
            leader = None
            dist = math.hypot(cx - ax, cy - ay)
            if dist > min_leader_px:
                leader = f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{cx:.2f}" y2="{cy:.2f}" stroke="#000000" stroke-width="0.2mm"/>'
            return cx, cy, leader

    # если все пересекают, используем первый с выноской
    cx, cy = candidates[0]
    leader = f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{cx:.2f}" y2="{cy:.2f}" stroke="#000000" stroke-width="0.2mm"/>'
    return cx, cy, leader


