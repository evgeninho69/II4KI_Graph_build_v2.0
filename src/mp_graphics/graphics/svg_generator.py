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

    def _find_best_leader_direction(self, point_x: float, point_y: float, 
                                  existing_labels: List[Dict], polygon_points: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Находит оптимальное направление для выноски, избегая ближайшие надписи"""
        # Направления для тестирования (8 основных направлений)
        directions = [
            (1, 0),   # Вправо
            (0, -1),  # Вверх
            (-1, 0),  # Влево
            (0, 1),   # Вниз
            (0.707, -0.707),  # Вправо-вверх
            (-0.707, -0.707), # Влево-вверх
            (-0.707, 0.707),  # Влево-вниз
            (0.707, 0.707),   # Вправо-вниз
        ]
        
        best_direction = (1, 0)  # По умолчанию вправо
        max_min_distance = 0
        
        for dx, dy in directions:
            # Нормализуем направление
            length = (dx**2 + dy**2)**0.5
            if length > 0:
                dx_norm = dx / length
                dy_norm = dy / length
                
                # Вычисляем минимальное расстояние до существующих надписей в этом направлении
                min_distance = float('inf')
                for label in existing_labels:
                    label_x, label_y = label['x'], label['y']
                    
                    # Вектор от точки к надписи
                    vec_x = label_x - point_x
                    vec_y = label_y - point_y
                    vec_length = (vec_x**2 + vec_y**2)**0.5
                    
                    if vec_length > 0:
                        # Нормализуем вектор
                        vec_x_norm = vec_x / vec_length
                        vec_y_norm = vec_y / vec_length
                        
                        # Скалярное произведение для определения "похожести" направлений
                        dot_product = dx_norm * vec_x_norm + dy_norm * vec_y_norm
                        
                        # Если направления похожи (dot_product > 0.5), учитываем расстояние
                        if dot_product > 0.5:
                            min_distance = min(min_distance, vec_length)
                
                # Если это направление дает больше места, выбираем его
                if min_distance > max_min_distance:
                    max_min_distance = min_distance
                    best_direction = (dx_norm, dy_norm)
        
        return best_direction
    
    def _detect_point_clusters(self, point_data: List[Dict], cluster_radius: float = 30) -> List[List[int]]:
        """Обнаруживает кластеры близко расположенных точек"""
        clusters = []
        used_points = set()
        
        for i, pd1 in enumerate(point_data):
            if i in used_points:
                continue
                
            cluster = [i]
            used_points.add(i)
            
            # Ищем точки в радиусе cluster_radius
            for j, pd2 in enumerate(point_data):
                if j <= i or j in used_points:
                    continue
                    
                distance = ((pd1['x_rel'] - pd2['x_rel'])**2 + (pd1['y_rel'] - pd2['y_rel'])**2)**0.5
                if distance <= cluster_radius:
                    cluster.append(j)
                    used_points.add(j)
            
            clusters.append(cluster)
        
        return clusters
    
    def _get_fan_angles(self, cluster_size: int, base_angle: float) -> List[float]:
        """Возвращает углы для веерного размещения подписей кластера"""
        if cluster_size == 1:
            return [base_angle]
        
        # Веерное размещение: распределяем углы в секторе 120 градусов
        fan_width = math.radians(120)  # 120 градусов в радианах
        start_angle = base_angle - fan_width / 2
        
        angles = []
        for i in range(cluster_size):
            if cluster_size > 1:
                angle_step = fan_width / (cluster_size - 1)
                angle = start_angle + i * angle_step
            else:
                angle = base_angle
            angles.append(angle)
        
        return angles
    
    def _spiral_search_for_label(self, start_x: float, start_y: float, label_text: str, font_size: float,
                                polygon_points_rel: List[Tuple[float, float]], all_object_buffers: List, 
                                existing_labels: List[Dict]) -> Tuple[float, float]:
        """Спиральный поиск места для размещения подписи без пересечений"""
        
        # Вычисляем размеры прямоугольника-обертки для подписи
        char_width = font_size * 0.6
        text_width = len(label_text) * char_width
        text_height = font_size
        padding = 4
        
        def create_label_rect(cx, cy):
            """Создает прямоугольник-обертку с центром в (cx, cy)"""
            return (
                cx - text_width/2 - padding,
                cy - text_height/2 - padding,
                cx + text_width/2 + padding,
                cy + text_height/2 + padding
            )
        
        def has_intersections(rect):
            """Проверяет пересечения прямоугольника со всеми объектами"""
            # Проверка пересечений с другими подписями
            for label in existing_labels:
                if self._bboxes_intersect(rect, label['bbox']):
                    return True
            
            # Проверка пересечений с буферами объектов
            for obj_buffer in all_object_buffers:
                if self._bboxes_intersect(rect, obj_buffer):
                    return True
            
            # Проверка, что прямоугольник снаружи полигона
            rect_center_x = (rect[0] + rect[2]) / 2
            rect_center_y = (rect[1] + rect[3]) / 2
            if self._point_inside_polygon(rect_center_x, rect_center_y, polygon_points_rel):
                return True
            
            # Проверка минимального расстояния до границы полигона
            min_dist = self._distance_to_polygon_edge(rect_center_x, rect_center_y, polygon_points_rel)
            if min_dist < 6:
                return True
            
            return False
        
        # Спиральный поиск
        max_radius = 150  # Максимальный радиус поиска
        step_size = 2
        
        for radius in range(0, max_radius, step_size):
            # Количество точек на окружности зависит от радиуса
            num_points = max(8, int(2 * math.pi * radius / 10)) if radius > 0 else 1
            
            for i in range(num_points):
                if radius == 0:
                    # Центральная точка
                    test_x, test_y = start_x, start_y
                else:
                    # Точки на окружности
                    angle = i * 2 * math.pi / num_points
                    test_x = start_x + radius * math.cos(angle)
                    test_y = start_y + radius * math.sin(angle)
                
                # Создаем прямоугольник-обертку
                test_rect = create_label_rect(test_x, test_y)
                
                # Проверяем пересечения
                if not has_intersections(test_rect):
                    return test_x, test_y
        
        # Fallback: если не нашли место, размещаем справа с максимальным отступом
        fallback_x = start_x + max_radius
        fallback_y = start_y
        return fallback_x, fallback_y
    
    def _find_position_near_point(self, start_x: float, start_y: float, label_text: str, font_size: float,
                                 all_object_buffers: List, existing_labels: List[Dict], 
                                 polygon_points: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Находит позицию для подписи рядом с точкой (как в CH)"""
        
        # Вычисляем размеры прямоугольника-обертки для подписи
        char_width = font_size * 0.6
        text_width = len(label_text) * char_width
        text_height = font_size
        padding = 4
        
        def create_label_rect(cx, cy):
            """Создает прямоугольник-обертку с центром в (cx, cy)"""
            return (
                cx - text_width/2 - padding,
                cy - text_height/2 - padding,
                cx + text_width/2 + padding,
                cy + text_height/2 + padding
            )
        
        def has_intersections(rect):
            """Проверяет пересечения прямоугольника со всеми объектами"""
            # Проверка пересечений с другими подписями
            for label in existing_labels:
                if self._bboxes_intersect(rect, label['bbox']):
                    return True
            
            # Проверка пересечений с буферами объектов
            for obj_buffer in all_object_buffers:
                if self._bboxes_intersect(rect, obj_buffer):
                    return True
            
            return False
        
        def is_inside_polygon(rect):
            """Проверяет, что подпись не попадает внутрь контура земельного участка"""
            # Проверяем центр прямоугольника подписи
            center_x = (rect[0] + rect[2]) / 2
            center_y = (rect[1] + rect[3]) / 2
            
            # Если центр внутри полигона, подпись не подходит
            if self._point_inside_polygon(center_x, center_y, polygon_points):
                return True
            
            # Дополнительно проверяем углы прямоугольника
            corners = [
                (rect[0], rect[1]),  # левый верхний
                (rect[2], rect[1]),  # правый верхний
                (rect[2], rect[3]),  # правый нижний
                (rect[0], rect[3])   # левый нижний
            ]
            
            # Если хотя бы один угол внутри полигона, подпись не подходит
            for corner_x, corner_y in corners:
                if self._point_inside_polygon(corner_x, corner_y, polygon_points):
                    return True
            
            return False
        
        # Пробуем разместить подпись рядом с точкой
        # Кандидаты: 4 квадранта рядом с точкой
        candidates = [
            (start_x, start_y),  # Точная позиция
            (start_x + 8, start_y),  # Справа
            (start_x, start_y - 8),  # Сверху
            (start_x - 8, start_y),  # Слева
            (start_x, start_y + 8),  # Снизу
        ]
        
        for test_x, test_y in candidates:
            test_rect = create_label_rect(test_x, test_y)
            
            # Проверяем, что подпись не пересекается с объектами И не попадает внутрь полигона
            if not has_intersections(test_rect) and not is_inside_polygon(test_rect):
                return test_x, test_y
        
        # Если не нашли место, возвращаем начальную позицию
        return start_x, start_y
    
    def _bboxes_intersect(self, bbox1: Tuple[float, float, float, float], bbox2: Tuple[float, float, float, float]) -> bool:
        """Проверяет пересечение двух прямоугольников"""
        return not (bbox1[2] < bbox2[0] or  # bbox1 левее bbox2
                   bbox1[0] > bbox2[2] or  # bbox1 правее bbox2
                   bbox1[3] < bbox2[1] or  # bbox1 выше bbox2
                   bbox1[1] > bbox2[3])    # bbox1 ниже bbox2
    
    def _distance_to_polygon_edge(self, x: float, y: float, polygon_points: List[Tuple[float, float]]) -> float:
        """Вычисляет минимальное расстояние от точки до границы полигона"""
        min_distance = float('inf')
        n = len(polygon_points)
        
        for i in range(n):
            j = (i + 1) % n
            x1, y1 = polygon_points[i]
            x2, y2 = polygon_points[j]
            
            # Расстояние от точки до отрезка
            distance = self._point_to_segment_distance(x, y, x1, y1, x2, y2)
            min_distance = min(min_distance, distance)
        
        return min_distance
    
    def _point_to_segment_distance(self, px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Вычисляет расстояние от точки до отрезка"""
        # Вектор отрезка
        dx = x2 - x1
        dy = y2 - y1
        
        # Если отрезок вырожден в точку
        if dx == 0 and dy == 0:
            return ((px - x1)**2 + (py - y1)**2)**0.5
        
        # Параметр t для проекции точки на прямую
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        
        # Ограничиваем t отрезком [0, 1]
        t = max(0, min(1, t))
        
        # Ближайшая точка на отрезке
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        
        # Расстояние до ближайшей точки
        return ((px - closest_x)**2 + (py - closest_y)**2)**0.5
    
    def _find_position_outside_polygon(self, point_x: float, point_y: float, 
                                     dx_norm: float, dy_norm: float, base_offset: float,
                                     polygon_points: List[Tuple[float, float]], 
                                     all_object_buffers: List[Tuple[float, float, float, float]] = None,
                                     label_text: str = "", font_size: float = 12) -> Tuple[float, float]:
        """Находит позицию для подписи снаружи полигона в заданном направлении"""
        max_attempts = 50
        offset_step = 2
        all_object_buffers = all_object_buffers or []
        
        for attempt in range(max_attempts):
            current_offset = base_offset + (attempt * offset_step)
            test_x = point_x + dx_norm * current_offset
            test_y = point_y + dy_norm * current_offset
            
            # Проверяем, что позиция снаружи полигона
            if not self._point_inside_polygon(test_x, test_y, polygon_points):
                # Дополнительно проверяем расстояние до границы
                distance_to_edge = self._distance_to_polygon_edge(test_x, test_y, polygon_points)
                if distance_to_edge >= 8:  # Увеличиваем минимальное расстояние до 8px
                    # Проверяем пересечения с буферами объектов
                    if label_text and all_object_buffers:
                        # Создаем bbox для подписи
                        char_width = font_size * 0.6
                        text_width = len(label_text) * char_width
                        text_height = font_size
                        padding = 6
                        label_bbox = (
                            test_x - padding,
                            test_y - text_height - padding,
                            test_x + text_width + padding,
                            test_y + padding
                        )
                        
                        # Проверяем пересечения с буферами объектов
                        has_buffer_conflict = any(
                            not (label_bbox[2] < buf[0] or label_bbox[0] > buf[2] or 
                                label_bbox[3] < buf[1] or label_bbox[1] > buf[3])
                            for buf in all_object_buffers
                        )
                        
                        if not has_buffer_conflict:
                            return test_x, test_y
                    else:
                        return test_x, test_y
        
        # Если не нашли подходящую позицию, возвращаем максимальный отступ
        fallback_offset = base_offset + (max_attempts * offset_step)
        return (
            point_x + dx_norm * fallback_offset,
            point_y + dy_norm * fallback_offset
        )
    
    def _place_leader_outside_polygon(self, point_x: float, point_y: float, direction: Tuple[float, float],
                                    radius_px: float, label_text: str, font_size: float, 
                                    polygon_points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
        """Размещает выноску ЗА ПРЕДЕЛАМИ контура земельного участка"""
        # Начинаем с минимального отступа от точки
        min_offset = radius_px + 5
        max_offset = 100  # Максимальное расстояние для поиска
        
        # Находим точку пересечения луча с границей полигона
        intersection_point = self._find_polygon_intersection(
            point_x, point_y, direction, polygon_points
        )
        
        if intersection_point:
            # Если есть пересечение, размещаем подпись за точкой пересечения
            intersect_x, intersect_y = intersection_point
            # Добавляем отступ за границей полигона
            label_x = intersect_x + direction[0] * 15
            label_y = intersect_y + direction[1] * 15
            leader_start_x = point_x + direction[0] * radius_px
            leader_start_y = point_y + direction[1] * radius_px
        else:
            # Если пересечения нет, ищем свободное место в заданном направлении
            for offset in range(int(min_offset), int(max_offset), 5):
                test_x = point_x + direction[0] * offset
                test_y = point_y + direction[1] * offset
                
                # Проверяем, что подпись снаружи полигона
                if not self._point_inside_polygon(test_x, test_y, polygon_points):
                    # Проверяем, что bbox подписи тоже снаружи
                    test_bbox = self._get_label_bbox(test_x, test_y, label_text, font_size)
                    bbox_center_x = (test_bbox[0] + test_bbox[2]) / 2
                    bbox_center_y = (test_bbox[1] + test_bbox[3]) / 2
                    
                    if not self._point_inside_polygon(bbox_center_x, bbox_center_y, polygon_points):
                        label_x = test_x
                        label_y = test_y
                        leader_start_x = point_x + direction[0] * radius_px
                        leader_start_y = point_y + direction[1] * radius_px
                        break
            else:
                # Fallback: размещаем в максимальном отступе
                label_x = point_x + direction[0] * max_offset
                label_y = point_y + direction[1] * max_offset
                leader_start_x = point_x + direction[0] * radius_px
                leader_start_y = point_y + direction[1] * radius_px
        
        return label_x, label_y, leader_start_x, leader_start_y
    
    def _find_polygon_intersection(self, start_x: float, start_y: float, direction: Tuple[float, float],
                                 polygon_points: List[Tuple[float, float]]) -> Tuple[float, float] | None:
        """Находит точку пересечения луча с границей полигона"""
        dx, dy = direction
        n = len(polygon_points)
        closest_intersection = None
        min_distance = float('inf')
        
        for i in range(n):
            j = (i + 1) % n
            x1, y1 = polygon_points[i]
            x2, y2 = polygon_points[j]
            
            # Проверяем пересечение луча с отрезком
            intersection = self._ray_segment_intersection(
                start_x, start_y, dx, dy, x1, y1, x2, y2
            )
            
            if intersection:
                ix, iy = intersection
                distance = ((ix - start_x)**2 + (iy - start_y)**2)**0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_intersection = (ix, iy)
        
        return closest_intersection
    
    def _ray_segment_intersection(self, ray_x: float, ray_y: float, ray_dx: float, ray_dy: float,
                                seg_x1: float, seg_y1: float, seg_x2: float, seg_y2: float) -> Tuple[float, float] | None:
        """Находит пересечение луча с отрезком"""
        # Параметрические уравнения
        # Луч: P = (ray_x, ray_y) + t * (ray_dx, ray_dy), t >= 0
        # Отрезок: Q = (seg_x1, seg_y1) + s * (seg_x2 - seg_x1, seg_y2 - seg_y1), 0 <= s <= 1
        
        seg_dx = seg_x2 - seg_x1
        seg_dy = seg_y2 - seg_y1
        
        # Решаем систему уравнений
        det = ray_dx * seg_dy - ray_dy * seg_dx
        if abs(det) < 1e-10:  # Параллельные линии
            return None
        
        t = (seg_dx * (ray_y - seg_y1) - seg_dy * (ray_x - seg_x1)) / det
        s = (ray_dx * (ray_y - seg_y1) - ray_dy * (ray_x - seg_x1)) / det
        
        if t >= 0 and 0 <= s <= 1:  # Пересечение найдено
            return (ray_x + t * ray_dx, ray_y + t * ray_dy)
        
        return None
    
    def _point_inside_polygon(self, x: float, y: float, polygon_points: List[Tuple[float, float]]) -> bool:
        """Проверяет, находится ли точка внутри полигона (алгоритм ray casting)"""
        n = len(polygon_points)
        inside = False
        j = n - 1
        
        for i in range(n):
            xi, yi = polygon_points[i]
            xj, yj = polygon_points[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def _get_label_bbox(self, x: float, y: float, text: str, font_size: float) -> Tuple[float, float, float, float]:
        """Возвращает bbox подписи: (x_min, y_min, x_max, y_max)"""
        char_width = font_size * 0.6
        text_width = len(text) * char_width
        text_height = font_size
        padding = 2
        return (
            x - padding,
            y - text_height - padding,
            x + text_width + padding,
            y + padding
        )

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
        offsets_mm = [(1.0, -1.0), (-1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
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
        need_leader = (dx * dx + dy * dy) ** 0.5 > mm_to_px(0.8, self.config.dpi)
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
        # Смещение подписи на 0.8 мм вправо и 0.8 мм вверх
        dx = mm_to_px(0.8, self.config.dpi)
        dy = mm_to_px(0.8, self.config.dpi)
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

    def generate_sgp_graphics(self, parcels: List[Dict[str, Any]],
                              stations: List[Dict[str, Any]],
                              directions: List[Dict[str, Any]],
                              boundary_points: List[Dict[str, Any]]) -> str:
        """Генерация СГП без масштаба с переносом пунктов рядом с участком.
        1) Нормализуем контур участка в увеличенной области; 2) Вычисляем центроид в метрах и px;
        3) Каждую станцию переносим на окружность вокруг участка, сохраняя азимут от центроида;
        4) Рисуем направления от перенесённых станций к точке н1 с подписями расстояний.
        Дополнительно: контур ЗУ рисуется по сегментам с цветами как в CH, точки границы
        отображаются с подписями; возле станций печатаются их координаты X/Y.
        """
        if not boundary_points:
            return ""

        # Используем рабочую область как в CH (с учётом полей, заголовка и легенды)
        original_width = self.config.width
        original_height = self.config.height
        # Получаем размеры рабочей области как в CH
        workarea_w, workarea_h = self._workarea_size_px()
        self.config.width = int(workarea_w)
        self.config.height = int(workarea_h)

        # Нормализуем контур ЗУ в увеличенной области
        coords = [(p.get('x', 0.0), p.get('y', 0.0)) for p in boundary_points]
        norm_pts, _, _ = self._normalize_coordinates(coords)
        # Уменьшаем видимый масштаб ЗУ на СГП, чтобы освободить место для пунктов
        parcel_scale = 0.7  # 70% от нормализованного размера
        if len(norm_pts) >= 3:
            cx_tmp = sum(x for x, _ in norm_pts) / len(norm_pts)
            cy_tmp = sum(y for _, y in norm_pts) / len(norm_pts)
            scaled = []
            for x, y in norm_pts:
                sx = cx_tmp + (x - cx_tmp) * parcel_scale
                sy = cy_tmp + (y - cy_tmp) * parcel_scale
                scaled.append((sx, sy))
            norm_pts = scaled
        parts: List[str] = []

        # Сначала вычисляем центрирование, потом рисуем контур

        # Вычисляем границы масштабированного участка
        min_x = min(x for x, _ in norm_pts)
        max_x = max(x for x, _ in norm_pts)
        min_y = min(y for _, y in norm_pts)
        max_y = max(y for _, y in norm_pts)
        
        # Центрируем участок в рабочей области
        parcel_width = max_x - min_x
        parcel_height = max_y - min_y
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        # Добавляем буферную зону для размещения станций и подписей
        buffer_zone = 150.0  # пикселей
        required_width = parcel_width + 2 * buffer_zone
        required_height = parcel_height + 2 * buffer_zone
        
        # Проверяем, помещается ли участок с буферной зоной
        if required_width > self.config.width or required_height > self.config.height:
            # Уменьшаем масштаб участка, чтобы поместился с буферной зоной
            scale_factor = min(
                (self.config.width - 2 * buffer_zone) / parcel_width,
                (self.config.height - 2 * buffer_zone) / parcel_height
            )
            # Пересчитываем координаты с новым масштабом
            new_norm_pts = []
            for x, y in norm_pts:
                new_x = center_x + (x - center_x) * scale_factor
                new_y = center_y + (y - center_y) * scale_factor
                new_norm_pts.append((new_x, new_y))
            norm_pts = new_norm_pts
            # Пересчитываем границы
            min_x = min(x for x, _ in norm_pts)
            max_x = max(x for x, _ in norm_pts)
            min_y = min(y for _, y in norm_pts)
            max_y = max(y for _, y in norm_pts)
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
        
        # Смещение для центрирования участка в рабочей области (как в CH)
        shift_x = self.config.width / 2 - center_x
        shift_y = self.config.height / 2 - center_y
        
        # Применяем смещение к участку
        norm_pts = [(x + shift_x, y + shift_y) for (x, y) in norm_pts]
        cx_px = center_x + shift_x
        cy_px = center_y + shift_y
        cx_m = sum(p.get('x', 0.0) for p in boundary_points) / len(boundary_points)
        cy_m = sum(p.get('y', 0.0) for p in boundary_points) / len(boundary_points)

        # Контур участка — по сегментам с цветами как в CH
        n = len(norm_pts)
        if n >= 2:
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = norm_pts[i]
                x2, y2 = norm_pts[j]
                k1 = str(boundary_points[i].get('kind', 'EXISTING'))
                k2 = str(boundary_points[j].get('kind', 'EXISTING'))
                if k1 in ('NEW', 'CREATED') or k2 in ('NEW', 'CREATED'):
                    seg_status = BoundaryStatus.NEW
                elif k1 == 'EXISTING' and k2 == 'EXISTING':
                    seg_status = BoundaryStatus.EXISTING
                else:
                    seg_status = BoundaryStatus.UNCERTAIN
                parts.append(self._draw_boundary_segment(x1, y1, x2, y2, seg_status))

        # Уменьшаем радиус кольца для станций - они должны быть ближе к участку
        max_dist_px = 0.0
        for x, y in norm_pts:
            d = ((x - cx_px)**2 + (y - cy_px)**2) ** 0.5
            max_dist_px = max(max_dist_px, d)
        buffer_px = 40.0  # уменьшенная буферная зона вокруг участка
        ring_r = max_dist_px + buffer_px  # минимально за пределами буфера
        # Гарантируем вхождение станций и их подписей в рабочую область
        pad = 80.0  # уменьшенный запас под подписи
        max_r_left = max(10.0, cx_px - pad)
        max_r_up = max(10.0, cy_px - pad)
        max_r_right = max(10.0, self.config.width - cx_px - pad)
        max_r_down = max(10.0, self.config.height - cy_px - pad)
        ring_r = min(max(ring_r, max_dist_px + buffer_px), max_r_left, max_r_up, max_r_right, max_r_down)

        # Находим точку н1 для направлений (первая точка по порядку, уже смещённая)
        point_n1 = boundary_points[0] if boundary_points else None
        point_n1_coords = norm_pts[0] if norm_pts else None

        # Определяем маркер стрелки для направлений
        parts.append(
            '<defs>'
            '  <marker id="sgp-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">'
            '    <path d="M0,0 L0,6 L6,3 z" fill="#0077CC" />'
            '  </marker>'
            '</defs>'
        )

        # Переносим станции по азимуту (используем смещённый центроид)
        placed: Dict[Any, Tuple[float, float]] = {}
        for st in stations or []:
            sid = st.get('id')
            sx_m = float(st.get('x', 0.0))
            sy_m = float(st.get('y', 0.0))
            ang = math.atan2(sy_m - cy_m, sx_m - cx_m)
            sx = cx_px + ring_r * math.cos(ang)
            sy = cy_px + ring_r * math.sin(ang)
            placed[sid] = (sx, sy)
            
            # Символ станции согласно типу: GGS (треугольник) или OMS (квадрат)
            kind = (st.get('kind') or 'OMS').upper()
            if kind == 'GGS':
                parts.append(self._create_triangle(sx, sy, size=5.0, fill="#fff", stroke=self.config.blue, stroke_width="0.5mm"))
                self.used_legend_tokens.add("ggs")
            else:
                parts.append(self._create_square(sx, sy, size=4.0, fill="#fff", stroke=self.config.blue, stroke_width="0.5mm"))
                parts.append(self._create_circle(sx, sy, r=0.8, fill=self.config.blue))
                self.used_legend_tokens.add("oms")
            
            # Подпись станции
            name = st.get('name') or st.get('id')
            if name:
                parts.append(self._create_text(sx + 6, sy - 6, str(name), fill=self.config.blue, font_size=self.config.font_size - 1, text_anchor="start"))
            
            # Координаты станции скрыты по требованиям СГП
            
            # Направление к точке н1 с подписью расстояния
            if point_n1_coords:
                # Вычисляем реальное расстояние в метрах
                real_distance = ((sx_m - point_n1.get('x', 0.0))**2 + (sy_m - point_n1.get('y', 0.0))**2)**0.5
                
                # Рисуем направление (синяя линия со стрелкой)
                line = self._create_line(sx, sy, point_n1_coords[0], point_n1_coords[1], 
                                         stroke=self.config.blue, stroke_width="0.2mm")
                # добавляем стрелку
                if 'marker-end' not in line:
                    parts.append(line.replace('/>', ' marker-end="url(#sgp-arrow)"/>'))
                else:
                    parts.append(line)
                
                # Подпись расстояния в середине линии
                mid_x = (sx + point_n1_coords[0]) / 2
                mid_y = (sy + point_n1_coords[1]) / 2
                parts.append(self._create_text(mid_x, mid_y - 8, f"{real_distance:.1f} м", 
                                             fill=self.config.blue, font_size=self.config.font_size - 2, text_anchor="middle"))
            
            self.used_legend_tokens.add("geodir-determine")

        # Создаем буферные зоны для точек и границ (как в CH)
        point_bboxes = []
        boundary_bboxes = []
        
        # Создаем буферы всех точек (используем локальные функции как в CH)
        def get_point_bbox(x, y, radius_px):
            """Создает bbox для точки с буферной зоной"""
            buffer = 8.0  # буферная зона в пикселях
            return (x - radius_px - buffer, y - radius_px - buffer, 
                   x + radius_px + buffer, y + radius_px + buffer)
        
        def get_boundary_buffer_zones(polygon_points):
            """Создает буферные зоны для всех границ полигона"""
            buffer_zones = []
            buffer = 8.0  # буферная зона в пикселях
            for i in range(len(polygon_points)):
                j = (i + 1) % len(polygon_points)
                x1, y1 = polygon_points[i]
                x2, y2 = polygon_points[j]
                
                # Создаем более точную буферную зону для сегмента границы
                # Учитываем направление линии и создаем буфер перпендикулярно к ней
                dx = x2 - x1
                dy = y2 - y1
                length = (dx*dx + dy*dy)**0.5
                
                if length > 0:
                    # Нормализуем направление
                    dx_norm = dx / length
                    dy_norm = dy / length
                    
                    # Создаем перпендикулярное направление для буфера
                    perp_x = -dy_norm * buffer
                    perp_y = dx_norm * buffer
                    
                    # Создаем 4 угла буферной зоны
                    corners = [
                        (x1 + perp_x, y1 + perp_y),  # перпендикуляр от начала
                        (x1 - perp_x, y1 - perp_y),  # перпендикуляр от начала (другая сторона)
                        (x2 - perp_x, y2 - perp_y),  # перпендикуляр от конца
                        (x2 + perp_x, y2 + perp_y)   # перпендикуляр от конца (другая сторона)
                    ]
                    
                    # Находим границы буферной зоны
                    min_x = min(corner[0] for corner in corners)
                    min_y = min(corner[1] for corner in corners)
                    max_x = max(corner[0] for corner in corners)
                    max_y = max(corner[1] for corner in corners)
                else:
                    # Fallback для нулевой длины
                    min_x = min(x1, x2) - buffer
                    min_y = min(y1, y2) - buffer
                    max_x = max(x1, x2) + buffer
                    max_y = max(y1, y2) + buffer
                
                buffer_zones.append((min_x, min_y, max_x, max_y))
            return buffer_zones
        
        # Создаем буферы всех точек
        for i, (bp, (x, y)) in enumerate(zip(boundary_points, norm_pts)):
            point_bbox = get_point_bbox(x, y, mm_to_px(POINT_DIAMETER_MM/2.0, self.config.dpi))
            point_bboxes.append(point_bbox)
        
        # Создаем буферы всех границ
        boundary_bboxes = get_boundary_buffer_zones(norm_pts)
        
        # Объединяем все буферы объектов (кроме подписей)
        all_object_buffers = point_bboxes + boundary_bboxes

        # Применяем полную систему размещения подписей точек из CH
        # Подготавливаем данные точек для системы размещения
        point_data = []
        for i, (bp, (x, y)) in enumerate(zip(boundary_points, norm_pts)):
            kind = str(bp.get('kind', 'EXISTING'))
            
            # Правильная нумерация: новые точки с префиксом "н", существующие без префикса
            if kind in ('NEW', 'CREATED'):
                status = PointStatus.NEW
                color = self.config.red
                lbl = f"н{i+1}"  # н1, н2, н3...
                self.used_legend_tokens.add("point-new")
                self.used_legend_tokens.add("label-point-new")
            elif kind == 'REMOVED':
                status = PointStatus.REMOVED
                color = self.config.black
                lbl = f"{i+1}"  # 1, 2, 3... (курсив+подчёркивание)
                self.used_legend_tokens.add("point-removed")
            else:
                status = PointStatus.EXISTING
                color = self.config.black
                lbl = f"{i+1}"  # 1, 2, 3...
                self.used_legend_tokens.add("point-existing")
                self.used_legend_tokens.add("label-point-existing")
            
            point_data.append({
                'x_abs': x,
                'y_abs': y,
                'x_rel': x,
                'y_rel': y,
                'label': lbl,
                'color': color,
                'status': status,
                'radius_mm': POINT_DIAMETER_MM/2.0,
                'radius_px': mm_to_px(POINT_DIAMETER_MM/2.0, self.config.dpi)
            })
        
        # Обнаруживаем кластеры точек для веерного размещения
        clusters = self._detect_point_clusters(point_data, cluster_radius=30)
        
        # Создаем карту углов для каждой точки
        point_angles = {}
        for cluster in clusters:
            if len(cluster) > 1:  # Только для кластеров из нескольких точек
                # Вычисляем базовый угол для кластера (от центра полигона)
                cluster_center_x = sum(point_data[idx]['x_abs'] for idx in cluster) / len(cluster)
                cluster_center_y = sum(point_data[idx]['y_abs'] for idx in cluster) / len(cluster)
                
                base_dx = cluster_center_x - cx_px
                base_dy = cluster_center_y - cy_px
                base_angle = math.atan2(base_dy, base_dx)
                
                # Получаем веерные углы для кластера
                fan_angles = self._get_fan_angles(len(cluster), base_angle)
                
                # Присваиваем углы точкам в кластере
                for i, point_idx in enumerate(cluster):
                    point_angles[point_idx] = fan_angles[i]
        
        # Создаем все буферы для проверки пересечений
        label_positions = []
        font_size_px = self.config.font_size
        
        # Спиральный поиск позиций для всех точек
        for i, pd in enumerate(point_data):
            # Используем веерный угол если точка в кластере, иначе направление от центра
            if i in point_angles:
                # Используем предварительно вычисленный веерный угол
                angle = point_angles[i]
                dx_norm = math.cos(angle)
                dy_norm = math.sin(angle)
            else:
                # Направление от центра наружу (для одиночных точек)
                dx = pd['x_abs'] - cx_px
                dy = pd['y_abs'] - cy_px
                dist = (dx**2 + dy**2)**0.5
                
                if dist > 0.1:
                    # Нормализуем направление
                    dx_norm = dx / dist
                    dy_norm = dy / dist
                else:
                    dx_norm, dy_norm = 1, 0  # Fallback направление
            
            # В SGP, как и в CH, подписи размещаются рядом с точками
            # Используем простой алгоритм размещения рядом с точкой
            base_offset = pd['radius_px'] + 4  # Минимальный отступ от точки
            start_x = pd['x_rel'] + dx_norm * base_offset
            start_y = pd['y_rel'] + dy_norm * base_offset
            
            # Простой поиск позиции рядом с точкой (как в CH)
            label_x, label_y = self._find_position_near_point(
                start_x, start_y, pd['label'], font_size_px,
                all_object_buffers, label_positions, norm_pts
            )
            
            # Создаем bbox для найденной позиции
            def get_label_bbox(cx, cy, text, fs):
                char_width = fs * 0.6
                text_width = len(text) * char_width
                text_height = fs
                padding = 4
                return (cx - text_width/2 - padding, cy - text_height/2 - padding, 
                       cx + text_width/2 + padding, cy + text_height/2 + padding)
            
            bbox = get_label_bbox(label_x, label_y, pd['label'], font_size_px)
            label_positions.append({'bbox': bbox, 'x': label_x, 'y': label_y})
        
        # Рисуем точки и подписи
        for i, pd in enumerate(point_data):
            # Рисуем точку
            parts.append(self._create_circle(pd["x_rel"], pd["y_rel"], r=f"{pd['radius_mm']}mm", fill=pd["color"]))
            
            # Рисуем подпись
            lp = label_positions[i]
            
            # В SGP, как и в CH, выноски НЕ РИСУЮТСЯ - подписи размещаются рядом с точками
            
            # Стиль подписи для прекращающих точек
            if pd['status'] == PointStatus.REMOVED:
                # Создаем текст с курсивом и подчёркиванием для прекращающих точек
                parts.append(f'<text x="{lp["x"]}" y="{lp["y"]}" fill="{pd["color"]}" font-size="{font_size_px}" font-family="{self.config.font_family}" text-anchor="start" font-style="italic" text-decoration="underline">{pd["label"]}</text>')
            else:
                parts.append(self._create_text(lp['x'], lp['y'], pd['label'], fill=pd['color'], 
                                             font_size=font_size_px, text_anchor="start"))

        # Восстанавливаем исходные размеры
        self.config.width = original_width
        self.config.height = original_height

        return "\n".join(parts)
    
    def generate_scheme_graphics(self, parcels: List[Dict[str, Any]], 
                               boundary_points: List[Dict[str, Any]]) -> str:
        """Генерирует схему расположения земельных участков (СРЗУ) согласно правилам"""
        if not parcels or not boundary_points:
            return ""
        
        # Извлекаем координаты границы
        coords = []
        for point in boundary_points:
            coords.append((point['x'], point['y']))
        
        # Нормализуем координаты
        normalized_coords, center, scale = self._normalize_coordinates(coords)
        
        svg_elements = []
        
        # Оставляем на схеме только основной участок
        main_parcels = [p for p in parcels if p.get('is_main') or p.get('status') == 'NEW']
        if not main_parcels and parcels:
            main_parcels = [parcels[0]]

        # Рисуем границы участка по сегментам с правильными цветами для СРЗУ
        if main_parcels and len(normalized_coords) >= 3:
            n = len(normalized_coords)
            for i in range(n):
                j = (i + 1) % n
                x1, y1 = normalized_coords[i]
                x2, y2 = normalized_coords[j]
                
                # Определяем статус сегмента по статусам конечных точек
                k1 = str(boundary_points[i].get('kind', 'EXISTING'))
                k2 = str(boundary_points[j].get('kind', 'EXISTING'))
                
                # Для СРЗУ: красные линии для новых границ, серые для существующих
                if k1 in ('NEW', 'CREATED') or k2 in ('NEW', 'CREATED'):
                    stroke = self.config.red  # Красный для новых границ
                    legend_token = "target"
                else:
                    stroke = "#808080"  # Серый для существующих границ (смежники)
                    legend_token = "adjacent"
                
                # Рисуем сегмент с увеличенной толщиной для схемы
                line = self._create_line(x1, y1, x2, y2, stroke=stroke, stroke_width="2.5mm")
                svg_elements.append(line)
                self.used_legend_tokens.add(legend_token)
        
        # Рисуем упрощенные точки без детальных подписей (только для схемы)
        for i, norm_coord in enumerate(normalized_coords):
            x, y = norm_coord
            # Простые точки без подписей для схемы
            circle = self._create_circle(x, y, r="2mm", fill="#000000")
            svg_elements.append(circle)
        
        # Добавляем подпись участка в центре
        if main_parcels:
            parcel = main_parcels[0]
            label = ParcelLabelFormatter.build_parcel_label(parcel)
            if label:
                center_x = self.config.width / 2
                center_y = self.config.height / 2
                # Укорачиваем слишком длинные подписи для читаемости схемы
                display_label = label
                if len(display_label) > 20:
                    display_label = (display_label.split('/')[-1]) if ('/' in display_label) else display_label[-20:]
                parcel_label = self._create_text(center_x, center_y, display_label, 
                                               fill=self.config.black, font_size=9, text_anchor="middle")
                svg_elements.append(parcel_label)
                self.used_legend_tokens.add("label-parcel")
        
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
            # Схема расположения — упрощенная схема с кварталом и смежниками
            graphics = self.generate_scheme_graphics(parcels, boundary_points)
            svg_content.append(graphics)
            
        elif section_type == "SGP":
            # Схема геодезических построений — без масштаба: пункты располагаются рядом
            # с участком по реальному азимуту от центроида участка.
            sgp_graphics = self.generate_sgp_graphics(parcels, stations, directions, boundary_points)
            svg_content.append(sgp_graphics)
            
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

        # Центрирование: вычисляем отступы для размещения чертежа по центру рабочей области
        offset_x_px = max(0, (wa_w_px - content_w_px) / 2) if content_w_px < wa_w_px else 0
        offset_y_px = max(0, (wa_h_px - content_h_px) / 2) if content_h_px < wa_h_px else 0

        # Кол-во тайлов
        cols = max(1, int(math.ceil(content_w_px / wa_w_px)))
        rows = max(1, int(math.ceil(content_h_px / wa_h_px)))

        # Координатное преобразование "метры -> пиксели" с учетом центрирования
        def to_px(xm: float, ym: float) -> Tuple[float, float]:
            return (
                (xm - min_x) * px_per_meter + offset_x_px,
                # SVG y вниз, метры вверх
                content_h_px - (ym - min_y) * px_per_meter + offset_y_px,
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

                # Границы участка - рисуем по сегментам с классификацией по статусам точек
                contour = [(p['x'], p['y']) for p in points]
                pts_px = [to_px(x, y) for x, y in contour]
                # Смещаем координаты относительно окна тайла
                pts_px_shift = [(x - tile_x0, y - tile_y0) for x, y in pts_px]

                # Рисуем каждый сегмент границы отдельно с классификацией
                n = len(points)
                for i in range(n):
                    j = (i + 1) % n
                    x1_shift, y1_shift = pts_px_shift[i]
                    x2_shift, y2_shift = pts_px_shift[j]
                    
                    # Определяем статус сегмента по статусам конечных точек
                    # Согласно правилам: граница красная если ХОТЯ БЫ ОДНА точка новая
                    k1 = str(points[i].get('kind', 'EXISTING'))
                    k2 = str(points[j].get('kind', 'EXISTING'))
                    
                    # Устанавливаем цвет границы (красная для новых точек)
                    stroke = self.config.red if k1 in ('NEW', 'CREATED') or k2 in ('NEW', 'CREATED') else self.config.black
                    legend_token = "boundary-new" if stroke == self.config.red else "boundary-existing"
                    dash = None
                    
                    # Рисуем сегмент
                    parts.append(
                        f'<g clip-path="url(#{clip_id})"><line x1="{x1_shift:.2f}" y1="{y1_shift:.2f}" x2="{x2_shift:.2f}" y2="{y2_shift:.2f}" '
                        f'stroke="{stroke}" stroke-width="0.2mm"'
                        f'{f" stroke-dasharray=\"{dash}\"" if dash else ""}/></g>'
                    )
                    
                    # Добавляем токен в легенду
                    self.used_legend_tokens.add(legend_token)

                # Вычисляем центр полигона для размещения подписей снаружи
                def polygon_centroid(pts):
                    n = len(pts)
                    if n == 0:
                        return (0, 0)
                    cx = sum(p[0] for p in pts) / n
                    cy = sum(p[1] for p in pts) / n
                    return (cx, cy)
                
                pts_px_abs = [to_px(p['x'], p['y']) for p in points]
                center_x, center_y = polygon_centroid(pts_px_abs)
                
                # Функция для расчета размера буфера подписи (bbox)
                def get_label_bbox(x, y, text, font_size):
                    """Возвращает bbox подписи: (x_min, y_min, x_max, y_max)"""
                    # Примерная ширина символа = 0.6 * font_size
                    # Высота = font_size
                    char_width = font_size * 0.6
                    text_width = len(text) * char_width
                    text_height = font_size
                    
                    # Увеличиваем отступы для максимальной читаемости
                    padding = 6
                    return (
                        x - padding,
                        y - text_height - padding,
                        x + text_width + padding,
                        y + padding
                    )
                
                # Функция для расчета буфера точки (окружности)
                def get_point_bbox(x, y, radius_px):
                    """Возвращает bbox точки с буфером: (x_min, y_min, x_max, y_max)"""
                    # Буфер вокруг точки = радиус + отступ
                    buffer = radius_px + 6
                    return (
                        x - buffer,
                        y - buffer,
                        x + buffer,
                        y + buffer
                    )
                
                # Функция для расчета буфера границы (линии)
                def get_boundary_buffer_zones(polygon_points):
                    """Создает буферные зоны вокруг всех границ полигона"""
                    buffer_zones = []
                    n = len(polygon_points)
                    buffer_width = 8
                    
                    for i in range(n):
                        j = (i + 1) % n
                        x1, y1 = polygon_points[i]
                        x2, y2 = polygon_points[j]
                        
                        # Создаем буферную зону вокруг линии
                        buffer_zones.append(get_line_buffer_bbox(x1, y1, x2, y2, buffer_width))
                    
                    return buffer_zones
                
                def get_line_buffer_bbox(x1, y1, x2, y2, buffer_width):
                    """Возвращает bbox буферной зоны вокруг линии"""
                    # Находим минимальные и максимальные координаты
                    min_x = min(x1, x2) - buffer_width
                    max_x = max(x1, x2) + buffer_width
                    min_y = min(y1, y2) - buffer_width
                    max_y = max(y1, y2) + buffer_width
                    
                    return (min_x, min_y, max_x, max_y)
                
                def bboxes_intersect(bbox1, bbox2):
                    """Проверяет пересечение двух bbox"""
                    return not (bbox1[2] < bbox2[0] or  # bbox1 левее bbox2
                               bbox1[0] > bbox2[2] or  # bbox1 правее bbox2
                               bbox1[3] < bbox2[1] or  # bbox1 выше bbox2
                               bbox1[1] > bbox2[3])    # bbox1 ниже bbox2
                
                # Подготовка данных точек
                point_data = []
                created_index = 0
                existing_index = 0
                
                for i, (xm, ym) in enumerate(contour):
                    x_abs, y_abs = to_px(xm, ym)
                    x_rel = x_abs - tile_x0
                    y_rel = y_abs - tile_y0
                    kind = (points[i].get('kind') if i < len(points) else 'CREATED')
                    
                    if str(kind) in ('NEW', 'CREATED'):
                        col = self.config.red
                        created_index += 1
                        label_txt = f"н{created_index}"
                        point_radius = self.config.created_point_radius
                        self.used_legend_tokens.add("point-new")
                        self.used_legend_tokens.add("label-point-new")
                    else:
                        col = self.config.black
                        existing_index += 1
                        label_txt = f"{existing_index}"
                        point_radius = self.config.existing_point_radius
                        self.used_legend_tokens.add("point-existing")
                        self.used_legend_tokens.add("label-point-existing")
                    
                    point_data.append({
                        'x_abs': x_abs,
                        'y_abs': y_abs,
                        'x_rel': x_rel,
                        'y_rel': y_rel,
                        'label': label_txt,
                        'color': col,
                        'radius_mm': point_radius,
                        'radius_px': mm_to_px(point_radius, self.config.dpi)
                    })
                
                # Функция проверки пересечения с полигоном
                def point_inside_polygon(x, y, polygon_points):
                    """Проверяет, находится ли точка внутри полигона (алгоритм ray casting)"""
                    n = len(polygon_points)
                    inside = False
                    j = n - 1
                    
                    for i in range(n):
                        xi, yi = polygon_points[i]
                        xj, yj = polygon_points[j]
                        
                        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                            inside = not inside
                        j = i
                    
                    return inside
                
                # Создаем все буферы для проверки пересечений
                label_positions = []
                point_bboxes = []  # Буферы точек
                boundary_bboxes = []  # Буферы границ
                font_size_px = self.config.font_size
                
                # Создаем буферы всех точек
                for pd in point_data:
                    point_bbox = get_point_bbox(pd['x_rel'], pd['y_rel'], pd['radius_px'])
                    point_bboxes.append(point_bbox)
                
                # Создаем буферы всех границ
                boundary_bboxes = get_boundary_buffer_zones(pts_px_abs)
                
                # Объединяем все буферы объектов (кроме подписей)
                all_object_buffers = point_bboxes + boundary_bboxes
                
                # Обнаруживаем кластеры точек для веерного размещения
                clusters = self._detect_point_clusters(point_data, cluster_radius=30)
                
                # Создаем карту углов для каждой точки
                point_angles = {}
                for cluster in clusters:
                    if len(cluster) > 1:  # Только для кластеров из нескольких точек
                        # Вычисляем базовый угол для кластера (от центра полигона)
                        cluster_center_x = sum(point_data[idx]['x_abs'] for idx in cluster) / len(cluster)
                        cluster_center_y = sum(point_data[idx]['y_abs'] for idx in cluster) / len(cluster)
                        
                        base_dx = cluster_center_x - center_x
                        base_dy = cluster_center_y - center_y
                        base_angle = math.atan2(base_dy, base_dx)
                        
                        # Получаем веерные углы для кластера
                        fan_angles = self._get_fan_angles(len(cluster), base_angle)
                        
                        # Присваиваем углы точкам в кластере
                        for i, point_idx in enumerate(cluster):
                            point_angles[point_idx] = fan_angles[i]
                
                for i, pd in enumerate(point_data):
                    # Используем веерный угол если точка в кластере, иначе направление от центра
                    if i in point_angles:
                        # Используем предварительно вычисленный веерный угол
                        angle = point_angles[i]
                        dx_norm = math.cos(angle)
                        dy_norm = math.sin(angle)
                    else:
                        # Направление от центра наружу (для одиночных точек)
                        dx = pd['x_abs'] - center_x
                        dy = pd['y_abs'] - center_y
                        dist = (dx**2 + dy**2)**0.5
                        
                        if dist > 0.1:
                            # Нормализуем направление
                            dx_norm = dx / dist
                            dy_norm = dy / dist
                        else:
                            dx_norm, dy_norm = 1, 0  # Fallback направление
                    
                    # Начальная позиция для спирального поиска (относительные координаты)
                    base_offset = pd['radius_px'] + 8
                    start_x = pd['x_rel'] + dx_norm * base_offset
                    start_y = pd['y_rel'] + dy_norm * base_offset
                    
                    # Спиральный поиск оптимальной позиции для прямоугольника-обертки
                    label_x, label_y = self._spiral_search_for_label(
                        start_x, start_y, pd['label'], font_size_px,
                        pts_px_shift, all_object_buffers, label_positions
                    )
                    
                    # Создаем bbox для найденной позиции (прямоугольник-обертка уже учтен в спиральном поиске)
                    bbox = get_label_bbox(label_x, label_y, pd['label'], font_size_px)
                    
                    label_positions.append({'bbox': bbox, 'x': label_x, 'y': label_y})
                
                # Рисуем точки и подписи
                for i, pd in enumerate(point_data):
                    # Рисуем точку
                    parts.append(f'<g clip-path="url(#{clip_id})">{self._create_circle(pd["x_rel"], pd["y_rel"], r=f"{pd["radius_mm"]}mm", fill=pd["color"])}</g>')
                    
                    # Рисуем подпись
                    lp = label_positions[i]
                    parts.append(self._create_text(lp['x'], lp['y'], pd['label'], fill=pd['color'], font_size=font_size_px, text_anchor="start"))

                # Подпись участка в центре полигона (центроид)
                if parcels:
                    label = ParcelLabelFormatter.build_parcel_label(parcels[0])
                    # Используем центроид полигона вместо центра рабочей области
                    cx = center_x - tile_x0
                    cy = center_y - tile_y0
                    parts.append(self._create_text(cx, cy, label, fill=self.config.black, font_size=16, text_anchor="middle"))
                    # Добавляем токен для подписи участка в легенду
                    self.used_legend_tokens.add("label-parcel")

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
