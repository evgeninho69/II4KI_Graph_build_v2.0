"""
Построитель схемы расположения земельных участков по координатам.
Строит SVG-схему с правильным масштабом и обрезкой по области листа.
"""

import math
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
from ..datasource.json_contract import load_json
from ..graphics.labels import ParcelLabelFormatter
from ..core.units import mm_to_px


class SchemeLayoutBuilder:
    """Построитель схемы расположения земельных участков."""
    
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = None
        self.parcel_coordinates = []
        self.scale = 1.0
        self.bounds = None
        self.svg_bounds = (800, 600)  # Размер SVG области
        self.parcel_label = None
        self.offset_x = 50
        self.offset_y = 50
        self._placed_labels: List[Tuple[float, float, float, float]] = []  # x1,y1,x2,y2 для коллизий
        
    def parse_data(self):
        """Читает контракт JSON и извлекает основной контур ЗУ."""
        self.data = load_json(self.json_path)
        entities = self.data.get('entities', {})
        points = entities.get('boundary_points', []) or []
        self.parcel_coordinates = [(p['x'], p['y']) for p in points]
        parcels = entities.get('parcels', []) or []
        if parcels:
            self.parcel_label = ParcelLabelFormatter.build_parcel_label(parcels[0])
        else:
            self.parcel_label = ":ЗУ"
        logging.debug("SRZU parse: %d points, parcels=%d", len(self.parcel_coordinates), len(parcels))
    
    def _parse_parcel_file(self) -> List[Tuple[float, float]]:
        """Парсит координаты из текстового файла участка."""
        coordinates = []
        
        with open(self.parcel_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ';' in line:
                    parts = line.split(';')
                    if len(parts) == 2:
                        try:
                            x = float(parts[0].replace(',', '.'))
                            y = float(parts[1].replace(',', '.'))
                            coordinates.append((x, y))
                        except ValueError:
                            continue
        
        return coordinates
    
    def calculate_bounds_and_scale(self):
        """Определяет границы области и оптимальный масштаб."""
        # Фокусируемся на основном участке и близлежащих участках
        # Сначала определяем границы основного участка
        if not self.parcel_coordinates:
            raise ValueError("Не найдены координаты основного участка")
        
        # Границы основного участка
        main_min_x = min(coord[0] for coord in self.parcel_coordinates)
        main_max_x = max(coord[0] for coord in self.parcel_coordinates)
        main_min_y = min(coord[1] for coord in self.parcel_coordinates)
        main_max_y = max(coord[1] for coord in self.parcel_coordinates)
        
        # Добавляем буферную зону вокруг основного участка (например, 200 метров)
        buffer = 200.0  # метров
        min_x = main_min_x - buffer
        max_x = main_max_x + buffer
        min_y = main_min_y - buffer
        max_y = main_max_y + buffer
        
        self.bounds = {
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y,
            'width': max_x - min_x,
            'height': max_y - min_y
        }
        
        # Рассчитываем масштаб для размещения в SVG области
        # Добавляем отступы 100px по краям (50px с каждой стороны)
        margin_px = 100
        available_width = self.svg_bounds[0] - margin_px
        available_height = self.svg_bounds[1] - margin_px
        
        # Рассчитываем масштаб: сколько пикселей на метр
        # scale_x = пиксели / метры
        scale_x = available_width / self.bounds['width']
        scale_y = available_height / self.bounds['height']
        
        # Выбираем меньший масштаб для полного размещения
        calculated_scale = min(scale_x, scale_y)
        
        # Округляем до стандартного масштаба для читаемости
        # Стандартные масштабы в пикселях на метр: 2.0, 1.0, 0.5, 0.2, 0.1, 0.04, 0.02
        # Соответствуют масштабам 1:500, 1:1000, 1:2000, 1:5000, 1:10000, 1:25000, 1:50000
        standard_scales = [2.0, 1.0, 0.5, 0.2, 0.1, 0.04, 0.02]
        self.scale = min(standard_scales, key=lambda x: abs(x - calculated_scale))
        
        # Определяем числовой масштаб для отображения
        scale_map = {2.0: 500, 1.0: 1000, 0.5: 2000, 0.2: 5000, 0.1: 10000, 0.04: 25000, 0.02: 50000}
        self.scale_number = scale_map[self.scale]

        # Центрирование области построения
        width_px = self.bounds['width'] / self.scale
        height_px = self.bounds['height'] / self.scale
        self.offset_x = (margin_px/2) + max(0, (available_width - width_px) / 2)
        self.offset_y = (margin_px/2) + max(0, (available_height - height_px) / 2)

    def _compute_font_size(self) -> int:
        """Подбирает размер шрифта в пикселях в зависимости от масштаба."""
        # Больше при 1:500, меньше при 1:5000+
        sn = self.scale_number
        if sn <= 500:
            return 16
        if sn <= 1000:
            return 13
        if sn <= 2000:
            return 12
        if sn <= 5000:
            return 11
        # Rule 5.1: не опускаться ниже ~7 pt ≈ 9 px
        return max(10, 9)

    def _place_centered_label(self, x: float, y: float, text: str, base_fs: int, min_fs: int = 12) -> Tuple[float, float, int]:
        """Размещает подпись по центру ЗУ. Если есть пересечения, уменьшает шрифт, сохраняя центрирование.
        Без смещения (только уменьшение шрифта до min_fs). Возвращает координату (x,y) для <text> и фактический размер шрифта.
        """
        def bbox(cx, cy, fs):
            w = max(20.0, 0.6 * fs * len(text))
            h = fs * 1.2
            return (cx - w/2, cy - h, cx + w/2, cy), w, h
        def intersects(a, b):
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            return not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)

        fs = base_fs
        x1, y1, x2, y2 = (*bbox(x, y, fs)[0],)
        # Пробуем уменьшать шрифт, не двигая центр
        while any(intersects((x1, y1, x2, y2), r) for r in self._placed_labels) and fs > min_fs:
            fs -= 1
            x1, y1, x2, y2 = (*bbox(x, y, fs)[0],)
        self._placed_labels.append((x1, y1, x2, y2))
        return (x, y2, fs)
        
        print(f"Рассчитанный масштаб: {calculated_scale:.2f} пикселей/метр")
        print(f"Выбранный масштаб: 1:{self.scale_number} ({self.scale:.2f} пикселей/метр)")
        
        print(f"Основной участок:")
        print(f"  X: {main_min_x:.2f} - {main_max_x:.2f} (ширина: {main_max_x - main_min_x:.2f})")
        print(f"  Y: {main_min_y:.2f} - {main_max_y:.2f} (высота: {main_max_y - main_min_y:.2f})")
        print(f"Буферная область:")
        print(f"  X: {min_x:.2f} - {max_x:.2f} (ширина: {self.bounds['width']:.2f})")
        print(f"  Y: {min_y:.2f} - {max_y:.2f} (высота: {self.bounds['height']:.2f})")
        print(f"Выбранный масштаб: 1:{self.scale_number}")
    
    def filter_parcels_in_bounds(self) -> List[Dict]:
        """Фильтрует участки, попадающие в область чертежа."""
        if not self.bounds:
            raise ValueError("Границы не рассчитаны. Вызовите calculate_bounds_and_scale()")
        
        filtered_parcels = []
        
        for parcel in self.xml_data['parcels']:
            # Проверяем, есть ли у участка координаты
            if not parcel['coordinates']:
                continue
            
            # Проверяем, пересекается ли участок с буферной областью
            for contour in parcel['coordinates']:
                if self._contour_intersects_bounds(contour):
                    filtered_parcels.append(parcel)
                    break
        
        logging.debug("Участков в буферной области: %d", len(filtered_parcels))
        return filtered_parcels
    
    def _contour_intersects_bounds(self, contour: List[Tuple[float, float]]) -> bool:
        """Проверяет, пересекается ли контур с областью чертежа."""
        for x, y in contour:
            if (self.bounds['min_x'] <= x <= self.bounds['max_x'] and 
                self.bounds['min_y'] <= y <= self.bounds['max_y']):
                return True
        return False
    
    def coordinates_to_svg(self, coordinates: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Преобразует координаты в SVG координаты."""
        if not self.bounds:
            raise ValueError("Границы не рассчитаны")
        
        svg_coords = []
        for x, y in coordinates:
            # Переносим в начало координат (относительно левого нижнего угла буферной области)
            rel_x = x - self.bounds['min_x']
            rel_y = y - self.bounds['min_y']
            
            # Масштабируем: 1 метр = self.scale пикселей
            svg_x = rel_x / self.scale
            svg_y = rel_y / self.scale
            
            # Инвертируем Y (SVG Y растет вниз, а наши координаты растут вверх)
            svg_y = (self.bounds['height'] / self.scale) - svg_y
            
            # Добавляем отступы от краев SVG
            svg_x += self.offset_x
            svg_y += self.offset_y
            
            svg_coords.append((svg_x, svg_y))
        
        return svg_coords
    
    def generate_svg(self) -> str:
        """Генерирует SVG-код схемы расположения."""
        if not self.bounds:
            self.calculate_bounds_and_scale()
        
        # Фильтруем участки
        filtered_parcels = self.filter_parcels_in_bounds()
        
        svg_parts = []
        
        # Номер кадастрового квартала на схеме (в левом верхнем углу области)
        quarter_num = self.xml_data['cadastral_quarter'].get('cadastral_number') if self.xml_data and self.xml_data.get('cadastral_quarter') else ''
        if quarter_num:
            fs = self._compute_font_size()
            qx, qy, fs = self._place_centered_label(self.offset_x + 40, self.offset_y + 20, quarter_num, fs)
            svg_parts.append(f'<text x="{qx:.2f}" y="{qy:.2f}" fill="#0000FF" font-size="{fs}" font-family="Times New Roman, serif" text-anchor="middle" font-weight="700">{quarter_num}</text>')

        # Границы кадастрового квартала (синяя сплошная линия)
        for boundary in self.xml_data['quarter_boundaries']:
            svg_coords = self.coordinates_to_svg(boundary)
            if svg_coords:
                points_str = " ".join([f"{x:.2f},{y:.2f}" for x, y in svg_coords])
                svg_parts.append(f'<polygon points="{points_str}" fill="none" stroke="#0000FF" stroke-width="0.6"/>')
        
        # Смежные земельные участки (чёрные линии + подписи)
        for parcel in filtered_parcels:
            label_done = False
            for contour in parcel['coordinates']:
                svg_coords = self.coordinates_to_svg(contour)
                if svg_coords:
                    points_str = " ".join([f"{x:.2f},{y:.2f}" for x, y in svg_coords])
                    svg_parts.append(f'<polygon points="{points_str}" fill="none" stroke="#000000" stroke-width="0.6"/>')
                    if not label_done:
                        cx = sum(x for x, y in svg_coords) / len(svg_coords)
                        cy = sum(y for x, y in svg_coords) / len(svg_coords)
                        cadnum = parcel.get('cadastral_number') or ''
                        label = cadnum
                        if cadnum and ':' in cadnum:
                            last = cadnum.split(':')[-1]
                            if last:
                                label = f":{last}"
                        elif cadnum:
                            label = f":{cadnum}"
                        else:
                            label = ''
                        if label:
                            fs = self._compute_font_size()
                            tx, ty, fs = self._place_centered_label(cx, cy, label, fs, min_fs=12)
                            svg_parts.append(f'<text x="{tx:.2f}" y="{ty:.2f}" fill="#000000" stroke="#ffffff" stroke-width="0.8" paint-order="stroke" font-size="{fs}" font-family="Times New Roman, serif" text-anchor="middle" font-weight="700">{label}</text>')
                            label_done = True
        
        # Основной земельный участок (красная линия)
        if self.parcel_coordinates:
            svg_coords = self.coordinates_to_svg(self.parcel_coordinates)
            points_str = " ".join([f"{x:.2f},{y:.2f}" for x, y in svg_coords])
            svg_parts.append(f'<polygon points="{points_str}" fill="none" stroke="#FF0000" stroke-width="0.8"/>')
            
            # Обозначение участка в центре
            center_x = sum(x for x, y in svg_coords) / len(svg_coords)
            center_y = sum(y for x, y in svg_coords) / len(svg_coords)
            fs = self._compute_font_size()+1
            tx, ty, fs = self._place_centered_label(center_x, center_y, self.parcel_label, fs, min_fs=12)
            svg_parts.append(f'<text x="{tx:.2f}" y="{ty:.2f}" fill="#000000" stroke="#ffffff" stroke-width="0.8" paint-order="stroke" font-size="{fs}" font-family="Times New Roman, serif" text-anchor="middle" font-weight="700">{self.parcel_label}</text>')
        
        svg_content = f'''<svg width="{self.svg_bounds[0]}" height="{self.svg_bounds[1]}" viewBox="0 0 {self.svg_bounds[0]} {self.svg_bounds[1]}" xmlns="http://www.w3.org/2000/svg">
{chr(10).join(svg_parts)}
</svg>'''
        
        return svg_content


if __name__ == "__main__":
    # Пример запуска: чтение JSON и вывод SVG SRZU
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("json", help="Путь к cpp JSON")
    parser.add_argument("--out", default="out_srzus.svg")
    args = parser.parse_args()
    b = SchemeLayoutBuilder(args.json)
    b.parse_data()
    b.calculate_bounds_and_scale()
    svg = b.generate_svg()
    Path(args.out).write_text(svg, encoding='utf-8')
