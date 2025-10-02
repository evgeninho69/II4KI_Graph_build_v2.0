"""
Генератор SVG-графики для межевых планов
Создает SVG-изображения на основе CPP-данных в соответствии с требованиями ГОСТ
"""

import math
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from .labels import ParcelLabelFormatter, LegendBuilder
from ..core.enums import ParcelStatus, PointStatus, BoundaryStatus
from ..core.units import mm_to_px
from .styles import POINT_DIAMETER_MM


@dataclass
class SVGConfig:
    """Конфигурация для генерации SVG"""
    width: int = 800
    height: int = 600
    stroke_width: float = 0.2  # мм
    point_radius: float = 1.5  # мм
    # Радиусы характерных точек (в пикселях SVG)
    created_point_radius: float = 1.5  # мм
    existing_point_radius: float = 1.5  # мм
    font_size: int = 11
    font_family: str = "Times New Roman, serif"
    # Внутренние поля рабочей области, чтобы подписи и точки гарантированно попадали в рамку
    inner_margin_px: int = 60
    # Толщина границы ЗУ на чертеже
    boundary_stroke_width: float = 0.2  # мм
    # Минимальный кегль текста в пунктах (Rule 5.1: не менее ~7 pt)
    min_font_pt: float = 7.0
    
    # Цвета ACI
    red: str = "#FF0000"      # ACI 1 - новые элементы
    black: str = "#000000"    # ACI 7 - существующие элементы
    blue: str = "#0077CC"     # Кадастровые границы
    green: str = "#00AA00"    # Охранные зоны
    brown: str = "#8B4513"    # Здания и сооружения
    # Параметры листа и рабочей области (мм)
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_mm: float = 14.0
    header_height_mm: float = 18.0
    legend_height_mm: float = 40.0
    dpi: int = 96
    show_north_arrow: bool = False


class SVGGraphicsGenerator:
    """Генератор SVG-графики для межевых планов"""
    
    def __init__(self, config: SVGConfig = None):
        self.config = config or SVGConfig()
        self.elements = []
        # Токены реально использованных условных знаков для авто-легенды
        self.used_legend_tokens: set[str] = set()
        
    def _add_element(self, element: str):
        """Добавляет SVG-элемент в список"""
        self.elements.append(element)
    
    def _workarea_size_px(self) -> Tuple[float, float]:
        """Возвращает размеры рабочей области (px) с учётом полей, заголовка и легенды."""
        wa_w_mm = max(0.0, self.config.page_width_mm - 2.0 * self.config.margin_mm)
        wa_h_mm = max(0.0, self.config.page_height_mm - (2.0 * self.config.margin_mm + self.config.header_height_mm + self.config.legend_height_mm))
        return (
            mm_to_px(wa_w_mm, self.config.dpi),
            mm_to_px(wa_h_mm, self.config.dpi),
        )
    
    def _workarea_clip_rect(self) -> Tuple[float, float, float, float]:
        """Координаты клипа (px) в системе SVG (лево, верх, ширина, высота)."""
        wa_w_px, wa_h_px = self._workarea_size_px()
        # Рисуем внутри всей SVG, поэтому будем клиппировать по границам вьюпорта
        return (0.0, 0.0, wa_w_px, wa_h_px)
    
    def _normalize_coordinates(self, coords: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], Tuple[float, float], float]:
        """
        Нормализует координаты для отображения в SVG
        Возвращает нормализованные координаты, центр и масштаб
        """
        if not coords:
            return [], (0, 0), 1.0
            
        # Находим границы
        min_x = min(x for x, y in coords)
        max_x = max(x for x, y in coords)
        min_y = min(y for x, y in coords)
        max_y = max(y for x, y in coords)
        
        # Вычисляем размеры
        width = max_x - min_x
        height = max_y - min_y
        
        # Используем фиксированные внутренние поля в пикселях, чтобы всё гарантированно входило
        padding_px = float(self.config.inner_margin_px)
        # Вычисляем масштаб для размещения в SVG c учётом внутренних полей
        scale_x = (self.config.width - 2 * padding_px) / width if width > 0 else 1.0
        scale_y = (self.config.height - 2 * padding_px) / height if height > 0 else 1.0
        scale = min(scale_x, scale_y)
        
        # Центрируем
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        # Нормализуем координаты
        normalized = []
        for x, y in coords:
            norm_x = (x - center_x) * scale + self.config.width / 2
            norm_y = (y - center_y) * scale + self.config.height / 2
            normalized.append((norm_x, norm_y))
        
        return normalized, (center_x, center_y), scale
    
    def _create_polygon(self, coords: List[Tuple[float, float]], 
                       fill: str = "none", stroke: str = "#000000", 
                       stroke_width: float | str = None,
                       stroke_dasharray: str = None) -> str:
        """Создает SVG-полигон"""
        if len(coords) < 3:
            return ""
            
        points = " ".join([f"{x},{y}" for x, y in coords])
        stroke_w = stroke_width if stroke_width is not None else f"{self.config.stroke_width}mm"
        dash = f' stroke-dasharray="{stroke_dasharray}"' if stroke_dasharray else ""
        # Используем скругление, чтобы исключить визуальный пунктир из-за сабпиксельного рендеринга
        return f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" stroke-linecap="round" stroke-linejoin="round"{dash}/>'
    
    def _create_line(self, x1: float, y1: float, x2: float, y2: float,
                    stroke: str = "#000000", stroke_width: float | str = None,
                    stroke_dasharray: str = None) -> str:
        """Создает SVG-линию"""
        stroke_w = stroke_width if stroke_width is not None else f"{self.config.stroke_width}mm"
        dash = f' stroke-dasharray="{stroke_dasharray}"' if stroke_dasharray else ""
        
        return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{stroke_w}"{dash}/>'

    def _draw_boundary_segment(self, x1: float, y1: float, x2: float, y2: float, status: BoundaryStatus) -> str:
        """Рисует одну часть границы с учётом статуса и фиксированной толщины 0.2мм."""
        stroke = self.config.black
        dash = None
        token = "boundary-existing"
        if status == BoundaryStatus.NEW:
            stroke = self.config.red
            token = "boundary-new"
        elif status == BoundaryStatus.UNCERTAIN:
            stroke = self.config.black
            dash = "2mm 1mm"
            token = "boundary-uncertain"
        self.used_legend_tokens.add(token)
        return self._create_line(x1, y1, x2, y2, stroke=stroke, stroke_width="0.2mm", stroke_dasharray=dash)
    
    def _create_circle(self, cx: float, cy: float, r: float = None,
                      fill: str = "#000000", stroke: str = "none") -> str:
        """Создает SVG-круг (характерную точку)"""
        radius = r if r is not None else f"{self.config.point_radius}mm"
        
        return f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" stroke="{stroke}"/>'
    
    def _create_text(self, x: float, y: float, text: str, 
                    fill: str = "#000000", font_size: int = None,
                    text_anchor: str = "middle") -> str:
        """Создает SVG-текст"""
        font_sz = font_size or self.config.font_size
        # Rule 5.1: обеспечить минимальный размер шрифта 7 pt (~9.33 px при 96 DPI)
        min_font_px = int(round(self.config.min_font_pt * (96.0/72.0)))
        if font_sz < min_font_px:
            font_sz = min_font_px
        
        return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{font_sz}" font-family="{self.config.font_family}" text-anchor="{text_anchor}">{text}</text>'

    # --- Размещение подписей с выносками ---
    def _segments_intersect(self, ax, ay, bx, by, cx, cy, dx, dy) -> bool:
        def orient(px, py, qx, qy, rx, ry):
            return (qy - py) * (rx - qx) - (qx - px) * (ry - qy)
        o1 = orient(ax, ay, bx, by, cx, cy)
        o2 = orient(ax, ay, bx, by, dx, dy)
        o3 = orient(cx, cy, dx, dy, ax, ay)
        o4 = orient(cx, cy, dx, dy, bx, by)
        if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:
            # коллинеарные — проверим перекрытие по проекциям
            return not (max(ax, bx) < min(cx, dx) or max(cx, dx) < min(ax, bx) or max(ay, by) < min(cy, dy) or max(cy, dy) < min(ay, by))
        return (o1 * o2 <= 0) and (o3 * o4 <= 0)

    def _line_intersects_boundary(self, x1, y1, x2, y2) -> bool:
        segments = getattr(self, "_boundary_segments_px", [])
        for (sx1, sy1, sx2, sy2) in segments:
            if self._segments_intersect(x1, y1, x2, y2, sx1, sy1, sx2, sy2):
                return True
        return False

    def _place_label(self, x: float, y: float, text: str, fill: str, font_size: int = None, text_anchor: str = "start", extra_style: str = '') -> str:
        # Кандидаты смещений по квадрантам (мм)
        offsets_mm = [(2.0, -2.0), (-2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)]
        chosen = None
        for (dx_mm, dy_mm) in offsets_mm:
            dx = mm_to_px(dx_mm, self.config.dpi)
            dy = mm_to_px(dy_mm, self.config.dpi)
            # линия выноски от якоря к точке под текстом
            tx, ty = x + dx, y - dy
            if not self._line_intersects_boundary(x, y, tx, ty):
                chosen = (dx, dy)
                break
        if chosen is None:
            dx = mm_to_px(2.0, self.config.dpi)
            dy = mm_to_px(-2.0, self.config.dpi)
        else:
            dx, dy = chosen
        # Лидерная линия, если расстояние > 1.5 мм
        need_leader = (dx * dx + dy * dy) ** 0.5 > mm_to_px(1.5, self.config.dpi)
        leader = ''
        if need_leader:
            leader = self._create_line(x, y, x + dx, y - dy, stroke=fill, stroke_width=f"{self.config.stroke_width}mm")
        # Текст
        font_sz = font_size or self.config.font_size
        min_font_px = int(round(self.config.min_font_pt * (96.0/72.0)))
        if font_sz < min_font_px:
            font_sz = min_font_px
        style_attr = f' style="{extra_style}"' if extra_style else ''
        text_el = f'<text x="{x + dx}" y="{y - dy}" fill="{fill}" font-size="{font_sz}" font-family="{self.config.font_family}" text-anchor="{text_anchor}"{style_attr}>{text}</text>'
        return (leader + "\n" + text_el) if leader else text_el

    def _draw_point(self, x: float, y: float, status: PointStatus, label: str) -> str:
        radius_mm = POINT_DIAMETER_MM / 2.0
        color = self.config.red if (status == PointStatus.NEW) else self.config.black
        # Подготовка подписи
        txt = label
        if status == PointStatus.NEW and not (label.startswith('н') or label.startswith('Н')):
            txt = f"н{label}"
        # Смещение подписи на 1.5 мм вправо и 1.0 мм вверх
        dx = mm_to_px(1.5, self.config.dpi)
        dy = mm_to_px(1.0, self.config.dpi)
        # Точка
        circle = self._create_circle(x, y, r=f"{radius_mm}mm", fill=color)
        # Текст (REMOVED — курсив и подчёркивание)
        font_sz = max(self.config.font_size, int(round(self.config.min_font_pt * (96.0/72.0))))
        style_extra = ''
        if status == PointStatus.REMOVED:
            style_extra = ' font-style="italic" text-decoration="underline"'
        text_el = (
            f'<text x="{x + dx}" y="{y - dy}" fill="{color}" font-size="{font_sz}"'
            f' font-family="{self.config.font_family}" text-anchor="start"{style_extra}>{txt}</text>'
        )
        # Легенда
        if status == PointStatus.NEW:
            self.used_legend_tokens.add("point-new")
        elif status == PointStatus.REMOVED:
            self.used_legend_tokens.add("point-removed")
        else:
            self.used_legend_tokens.add("point-existing")
        return circle + "\n" + text_el
    
    def _create_triangle(self, cx: float, cy: float, size: float = 3.0,
                        fill: str = "#000000", stroke: str = "none", stroke_width: str | float | None = None) -> str:
        """Создает SVG-треугольник (пункт ГГС)"""
        # Вычисляем координаты треугольника
        h = size * math.sqrt(3) / 2
        x1, y1 = cx, cy - size
        x2, y2 = cx - size/2, cy + h
        x3, y3 = cx + size/2, cy + h
        
        points = f"{x1},{y1} {x2},{y2} {x3},{y3}"
        
        sw = '' if stroke_width is None else f' stroke-width="{stroke_width}"'
        return f'<polygon points="{points}" fill="{fill}" stroke="{stroke}"{sw}/>'
    
    def _create_square(self, cx: float, cy: float, size: float = 2.0,
                      fill: str = "#000000", stroke: str = "none", stroke_width: str | float | None = None) -> str:
        """Создает SVG-квадрат (пункт ОМС)"""
        half = size / 2
        x1, y1 = cx - half, cy - half
        x2, y2 = cx + half, cy + half
        
        sw = '' if stroke_width is None else f' stroke-width="{stroke_width}"'
        return f'<rect x="{x1}" y="{y1}" width="{size}" height="{size}" fill="{fill}" stroke="{stroke}"{sw}/>'
    
    def generate_parcel_graphics(self, parcels: List[Dict[str, Any]], 
                               boundary_points: List[Dict[str, Any]],
                               skip_point_labels: bool = False) -> str:
        """Генерирует графику для участков"""
        if not parcels or not boundary_points:
            return ""
        
        # Извлекаем координаты границы
        coords = []
        for point in boundary_points:
            coords.append((point['x'], point['y']))
        
        # Нормализуем координаты
        normalized_coords, center, scale = self._normalize_coordinates(coords)
        
        svg_elements = []
        
        # Оставляем на чертеже только основной участок (участок КР)
        # Пытаемся выбрать по признаку, иначе берём первый
        main_parcels = [p for p in parcels if p.get('is_main') or p.get('status') == 'NEW']
        if not main_parcels and parcels:
            main_parcels = [parcels[0]]

        # Рисуем границу участка по сегментам со статусами
        if main_parcels:
            n = len(normalized_coords)
            # Сохраняем сегменты для проверки пересечений выносок
            self._boundary_segments_px = []
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = normalized_coords[i]
                x2, y2 = normalized_coords[j]
                # Определяем статус по конечным точкам
                k1 = str(boundary_points[i].get('kind', 'EXISTING'))
                k2 = str(boundary_points[j].get('kind', 'EXISTING'))
                if k1 in ('NEW', 'CREATED') or k2 in ('NEW', 'CREATED'):
                    seg_status = BoundaryStatus.NEW
                elif k1 == 'EXISTING' and k2 == 'EXISTING':
                    seg_status = BoundaryStatus.EXISTING
                else:
                    # если смешанные или неизвестные — используем UNCERTAIN
                    seg_status = BoundaryStatus.UNCERTAIN
                svg_elements.append(self._draw_boundary_segment(x1, y1, x2, y2, seg_status))
                self._boundary_segments_px.append((x1, y1, x2, y2))
        
        created_index = 0
        existing_index = 0
        for i, (point, norm_coord) in enumerate(zip(boundary_points, normalized_coords)):
            x, y = norm_coord
            kind = point.get('kind', 'EXISTING')
            # Нормализуем статус
            if str(kind) in ('NEW', 'CREATED'):
                status = PointStatus.NEW
                created_index += 1
                lbl = f"{created_index}"
            elif str(kind) == 'REMOVED':
                status = PointStatus.REMOVED
                existing_index += 1
                lbl = f"{existing_index}"
            else:
                status = PointStatus.EXISTING
                existing_index += 1
                lbl = f"{existing_index}"
            # Рисуем точку и, при необходимости, подпись
            if skip_point_labels:
                # Только символ точки
                radius_mm = POINT_DIAMETER_MM / 2.0
                color = self.config.red if status == PointStatus.NEW else self.config.black
                svg_elements.append(self._create_circle(x, y, r=f"{radius_mm}mm", fill=color))
                token = "point-new" if status == PointStatus.NEW else ("point-removed" if status == PointStatus.REMOVED else "point-existing")
                self.used_legend_tokens.add(token)
            else:
                svg_elements.append(self._draw_point(x, y, status, lbl))
        
        # Добавляем подпись участка в центре
        if main_parcels:
            parcel = main_parcels[0]
            label = ParcelLabelFormatter.build_parcel_label(parcel)
            if label:
                center_x = self.config.width / 2
                center_y = self.config.height / 2
                # Укорачиваем слишком длинные подписи для читаемости SRZU
                display_label = label
                if len(display_label) > 20:
                    # Оставим правую часть после слеша или последние 20 символов
                    display_label = (display_label.split('/')[-1]) if ('/' in display_label) else display_label[-20:]
                parcel_label = self._place_label(center_x, center_y, display_label, fill=self.config.black, font_size=16, text_anchor="middle")
                svg_elements.append(parcel_label)
        
        return "\n".join(svg_elements)
    
    def generate_stations_graphics(self, stations: List[Dict[str, Any]]) -> str:
        """Генерирует графику для пунктов ОМС"""
        if not stations:
            return ""
        
        # Извлекаем координаты станций
        coords = []
        for station in stations:
            coords.append((station['x'], station['y']))
        
        # Нормализуем координаты
        normalized_coords, center, scale = self._normalize_coordinates(coords)
        
        svg_elements = []
        
        # Рисуем пункты ОМС/ГГС
        for station, norm_coord in zip(stations, normalized_coords):
            x, y = norm_coord
            name = station.get('name', '')
            kind = station.get('kind', 'OMS')
            
            # Рисуем символ в зависимости от типа
            if kind == 'GGS':  # Пункт ГГС
                symbol = self._create_triangle(x, y, fill="#fff", stroke=self.config.blue, stroke_width="0.5mm")
            else:  # Пункт ОМС
                symbol = self._create_square(x, y, fill="#fff", stroke=self.config.blue, stroke_width="0.5mm")
                # Добавляем точку в центре
                dot = self._create_circle(x, y, r=0.5, fill=self.config.blue)
                svg_elements.append(dot)
            
            svg_elements.append(symbol)
            if kind == 'GGS':
                self.used_legend_tokens.add("ggs")
            
            # Рисуем подпись
            if name:
                text = self._create_text(
                    x + 6, y - 6, name, 
                    fill=self.config.blue, 
                    font_size=self.config.font_size - 1,
                    text_anchor="start"
                )
                svg_elements.append(text)
        
        return "\n".join(svg_elements)
    
    def generate_directions_graphics(self, directions: List[Dict[str, Any]], 
                                   stations: List[Dict[str, Any]],
                                   boundary_points: List[Dict[str, Any]]) -> str:
        """Генерирует графику направлений для СГП"""
        if not directions or not stations or not boundary_points:
            return ""
        
        # Создаем словари для быстрого поиска
        stations_dict = {s['id']: s for s in stations}
        points_dict = {p['id']: p for p in boundary_points}
        
        # Собираем все координаты для нормализации
        all_coords = []
        for station in stations:
            all_coords.append((station['x'], station['y']))
        for point in boundary_points:
            all_coords.append((point['x'], point['y']))
        
        # Нормализуем координаты
        normalized_coords, center, scale = self._normalize_coordinates(all_coords)
        
        # Создаем словари нормализованных координат
        norm_stations = {}
        norm_points = {}
        
        for i, station in enumerate(stations):
            norm_stations[station['id']] = normalized_coords[i]
        
        for i, point in enumerate(boundary_points):
            norm_points[point['id']] = normalized_coords[len(stations) + i]
        
        svg_elements = []
        
        # Определяем маркер стрелки
        defs = (
            '<defs>'
            '  <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">'
            '    <path d="M0,0 L0,6 L6,3 z" fill="#0077CC" />'
            '  </marker>'
            '</defs>'
        )
        svg_elements.append(defs)

        # Рисуем направления
        for direction in directions:
            from_station_id = direction.get('from_station_id')
            to_point_id = direction.get('to_point_id')
            length = direction.get('length_m_int', 0)
            dtype = (direction.get('type') or 'DETERMINE').upper()
            
            if from_station_id in norm_stations and to_point_id in norm_points:
                x1, y1 = norm_stations[from_station_id]
                x2, y2 = norm_points[to_point_id]
                
                # Рисуем линию направления
                stroke_w = "0.5mm" if dtype == 'CREATE' else "0.2mm"
                line = self._create_line(
                    x1, y1, x2, y2,
                    stroke=self.config.blue,
                    stroke_width=stroke_w,
                    stroke_dasharray=None
                )
                svg_elements.append(line.replace('/>', f' marker-end="url(#arrowhead)"/>'))
                # Легенда направлений
                self.used_legend_tokens.add("geodir-create" if dtype == 'CREATE' else "geodir-determine")
                
                # Вычисляем середину линии для подписи расстояния
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                
                # Рисуем подпись расстояния
                distance_text = self._create_text(
                    mid_x, mid_y - 3, f"{length}м",
                    fill=self.config.blue,
                    font_size=self.config.font_size - 2,
                    text_anchor="middle"
                )
                svg_elements.append(distance_text)
        
        return "\n".join(svg_elements)
    
    def generate_complete_svg(self, cpp_data: Dict[str, Any], 
                            section_type: str = "DRAWING") -> str:
        """
        Генерирует полный SVG для указанного раздела
        section_type: "SCHEME", "SGP", "DRAWING"
        """
        if not cpp_data or 'entities' not in cpp_data:
            return ""
        
        entities = cpp_data['entities']
        parcels = entities.get('parcels', [])
        boundary_points = entities.get('boundary_points', [])
        stations = entities.get('stations', [])
        directions = entities.get('directions', [])
        
        # Начинаем SVG
        svg_content = [
            f'<svg width="{self.config.width}" height="{self.config.height}" viewBox="0 0 {self.config.width} {self.config.height}" xmlns="http://www.w3.org/2000/svg">'
        ]
        
        # Добавляем графику в зависимости от типа раздела
        if section_type == "SCHEME":
            # Схема расположения — оцениваем "плотность" точек и при сильной плотности не подписываем точки
            # Простой критерий: средняя длина ребра < 3мм в текущем вью — отключаем подписи точек
            skip_labels = False
            try:
                coords = [(p['x'], p['y']) for p in boundary_points]
                norm, _, _ = self._normalize_coordinates(coords)
                if len(norm) >= 2:
                    segs = 0
                    total = 0.0
                    for i in range(len(norm)):
                        x1, y1 = norm[i]
                        x2, y2 = norm[(i+1) % len(norm)]
                        d = ((x2 - x1)**2 + (y2 - y1)**2) ** 0.5
                        total += d
                        segs += 1
                    avg = total / max(1, segs)
                    if avg < mm_to_px(3.0, self.config.dpi):
                        skip_labels = True
            except Exception:
                skip_labels = False
            graphics = self.generate_parcel_graphics(parcels, boundary_points, skip_point_labels=skip_labels)
            svg_content.append(graphics)
            
        elif section_type == "SGP":
            # Схема геодезических построений - направления и пункты
            station_graphics = self.generate_stations_graphics(stations)
            direction_graphics = self.generate_directions_graphics(directions, stations, boundary_points)
            svg_content.extend([station_graphics, direction_graphics])
            
        elif section_type == "DRAWING":
            # Чертеж: только ЗУ и его характерные точки, без пунктов и направлений
            parcel_graphics = self.generate_parcel_graphics(parcels, boundary_points)
            svg_content.append(parcel_graphics)
        
        # Закрываем SVG
        svg_content.append('</svg>')
        
        return "\n".join(filter(None, svg_content))

    def _split_points_by_vertical_median(self, points: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Разбивает характерные точки по вертикальной медиане X на 2 группы (простой сплит)."""
        if not points:
            return [points]
        xs = sorted(p.get('x', 0.0) for p in points)
        median_x = xs[len(xs)//2]
        left = [p for p in points if p.get('x', 0.0) <= median_x]
        right = [p for p in points if p.get('x', 0.0) > median_x]
        return [left, right]

    def generate_drawings_paginated(self, cpp_data: Dict[str, Any]) -> List[str]:
        """Пагинация CH по тайлам формата листа (A3/A4) с клипом и дублированием меток на границах."""
        if not cpp_data or 'entities' not in cpp_data:
            return []
        entities = cpp_data['entities']
        parcels = entities.get('parcels', [])
        points = entities.get('boundary_points', [])
        if not points:
            return [self.generate_complete_svg(cpp_data, section_type="DRAWING")]

        # Геометрическая область в метрах
        xs = [p['x'] for p in points]
        ys = [p['y'] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width_m = max(1e-6, max_x - min_x)
        height_m = max(1e-6, max_y - min_y)

        # Параметры рабочей области
        wa_w_px, wa_h_px = self._workarea_size_px()
        # Масштаб по нормативному масштабу: 1:S
        scale_list = cpp_data.get('scales_allowed') or [500]
        S = float(scale_list[0])
        px_per_mm = mm_to_px(1.0, self.config.dpi)
        px_per_meter = px_per_mm * 1000.0 / S

        # Размер контента в пикселях при фиксированном масштабе
        content_w_px = width_m * px_per_meter
        content_h_px = height_m * px_per_meter

        # Кол-во тайлов
        cols = max(1, int(math.ceil(content_w_px / wa_w_px)))
        rows = max(1, int(math.ceil(content_h_px / wa_h_px)))

        # Координатное преобразование "метры -> пиксели"
        def to_px(xm: float, ym: float) -> Tuple[float, float]:
            return (
                (xm - min_x) * px_per_meter,
                # SVG y вниз, метры вверх
                content_h_px - (ym - min_y) * px_per_meter,
            )

        # Разбиваем рабочую область на сетку тайлов
        svgs: List[str] = []
        label_pad_px = mm_to_px(3.0, self.config.dpi)  # запас для меток

        for r in range(rows):
            for c in range(cols):
                # Сбрасываем токены легенды для страницы
                self.used_legend_tokens = set()
                # Порог тайла в пикселях
                tile_x0 = c * wa_w_px
                tile_y0 = r * wa_h_px
                tile_x1 = tile_x0 + wa_w_px
                tile_y1 = tile_y0 + wa_h_px

                # Собираем элементы
                parts: List[str] = []
                # clipPath
                clip_id = f"clip_ch_{r}_{c}"
                parts.append(
                    f'<defs><clipPath id="{clip_id}"><rect x="{tile_x0 - label_pad_px:.2f}" y="{tile_y0 - label_pad_px:.2f}" width="{wa_w_px + 2*label_pad_px:.2f}" height="{wa_h_px + 2*label_pad_px:.2f}"/></clipPath></defs>'
                )

                # Полигон участка
                contour = [(p['x'], p['y']) for p in points]
                pts_px = [to_px(x, y) for x, y in contour]
                # Смещаем полигон относительно окна тайла
                pts_px_shift = [(x - tile_x0, y - tile_y0) for x, y in pts_px]

                # Стиль границы по статусу
                parcel = parcels[0] if parcels else {}
                b_status = parcel.get('boundary_status') or parcel.get('status')
                stroke = self.config.black
                dash = None
                legend_token = "boundary-existing"
                stroke_w = "0.2mm"
                if str(b_status) == BoundaryStatus.NEW:
                    stroke = self.config.red
                    legend_token = "boundary-new"
                elif str(b_status) == BoundaryStatus.UNCERTAIN:
                    stroke = self.config.black
                    dash = "2mm 1mm"
                    legend_token = "boundary-uncertain"
                parts.append(
                    f'<g clip-path="url(#{clip_id})">{self._create_polygon(pts_px_shift, fill="none", stroke=stroke, stroke_width=stroke_w, stroke_dasharray=dash)}</g>'
                )
                self.used_legend_tokens.add(legend_token)

                # Точки и подписи
                created_index = 0
                existing_index = 0
                for i, (xm, ym) in enumerate(contour):
                    x, y = to_px(xm, ym)
                    x -= tile_x0
                    y -= tile_y0
                    kind = (points[i].get('kind') if i < len(points) else 'CREATED')
                    if str(kind) in ('NEW', 'CREATED'):
                        col = self.config.red
                        created_index += 1
                        label_txt = f"н{created_index}"
                        self.used_legend_tokens.add("point-new")
                    else:
                        col = self.config.black
                        existing_index += 1
                        label_txt = f"{existing_index}"
                        self.used_legend_tokens.add("point-existing")
                    parts.append(f'<g clip-path="url(#{clip_id})">{self._create_circle(x, y, r=f"{self.config.created_point_radius}mm" if str(kind) in ("NEW","CREATED") else f"{self.config.existing_point_radius}mm", fill=col)}</g>')
                    parts.append(self._create_text(x + 6, y - 6, label_txt, fill=col, font_size=self.config.font_size, text_anchor="start"))

                # Подпись участка в центре всей области (не тайла)
                if parcels:
                    label = ParcelLabelFormatter.build_parcel_label(parcels[0])
                    cx = content_w_px / 2 - tile_x0
                    cy = content_h_px / 2 - tile_y0
                    parts.append(self._create_text(cx, cy, label, fill=self.config.black, font_size=16, text_anchor="middle"))

                # Подсказка о продолжении
                page_num = r * cols + c + 1
                if cols * rows > 1:
                    for nbr in (page_num - 1, page_num + 1):
                        if 1 <= nbr <= cols * rows:
                            parts.append(self._create_text(wa_w_px - 8, wa_h_px - 8, f"см. лист {nbr}", fill=self.config.black, font_size=self.config.font_size - 1, text_anchor="end"))

                svg = "\n".join([
                    f'<svg width="{wa_w_px:.2f}" height="{wa_h_px:.2f}" viewBox="0 0 {wa_w_px:.2f} {wa_h_px:.2f}" xmlns="http://www.w3.org/2000/svg">',
                    *parts,
                    '</svg>'
                ])
                svgs.append(svg)
        return svgs
    
    def generate_legend_items(self, cpp_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Автогенерация легенды: используем реально применённые токены, иначе анализ данных."""
        if getattr(self, "used_legend_tokens", None):
            return LegendBuilder.build_from_tokens(self.used_legend_tokens)
        return LegendBuilder.generate_legend_items(cpp_data)


def generate_svg_for_section(cpp_data: Dict[str, Any], 
                           section_type: str = "DRAWING",
                           config: SVGConfig = None) -> str:
    """
    Удобная функция для генерации SVG для конкретного раздела
    """
    generator = SVGGraphicsGenerator(config)
    return generator.generate_complete_svg(cpp_data, section_type)


def generate_legend_for_data(cpp_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Удобная функция для генерации легенды (через LegendBuilder)."""
    return LegendBuilder.generate_legend_items(cpp_data)


if __name__ == "__main__":
    # Тестируем генератор SVG
    import json
    from pathlib import Path
    
    # Загружаем реальные данные
    data_file = Path(__file__).parent.parent.parent.parent.parent / "docs" / "МП" / "real_data_cpp.json"
    
    if data_file.exists():
        with open(data_file, 'r', encoding='utf-8') as f:
            cpp_data = json.load(f)
        
        # Генерируем SVG для разных разделов
        config = SVGConfig(width=800, height=600)
        
        for section in ["SCHEME", "SGP", "DRAWING"]:
            svg_content = generate_svg_for_section(cpp_data, section, config)
            
            output_file = data_file.parent / f"real_data_{section.lower()}.svg"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            
            print(f"SVG для раздела {section} сохранен в {output_file}")
        
        # Генерируем легенду
        legend_items = generate_legend_for_data(cpp_data)
        print(f"Сгенерировано {len(legend_items)} элементов легенды")
        for item in legend_items:
            print(f"  {item['text']}")
    else:
        print(f"Файл данных не найден: {data_file}")
