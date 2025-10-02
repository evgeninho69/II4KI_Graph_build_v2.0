from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
from xml.etree import ElementTree as ET

from .json_contract import SRZUData, Geometry
try:
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
except Exception:
    Polygon = None  # type: ignore
    MultiPolygon = None  # type: ignore
    unary_union = None  # type: ignore


def _coords_from_ordinates(ord_el) -> List[List[float]]:
    coords: List[List[float]] = []
    for o in ord_el.findall('ordinate'):
        try:
            x = float((o.findtext('x') or '').replace(',', '.'))
            y = float((o.findtext('y') or '').replace(',', '.'))
        except Exception:
            continue
        coords.append([x, y])
    return coords


def _polygon_centroid(coords: List[List[float]]) -> tuple[float, float]:
    """Вычисляет центроид полигона по координатам"""
    if not coords:
        return 0.0, 0.0
    area = 0.0
    cx = 0.0
    cy = 0.0
    pts = coords[:]
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area = area * 0.5
    if abs(area) < 1e-9:
        # fallback — среднее
        sx = sum(p[0] for p in coords) / len(coords)
        sy = sum(p[1] for p in coords) / len(coords)
        return sx, sy
    cx = cx / (6.0 * area)
    cy = cy / (6.0 * area)
    return cx, cy

def _polygon_from_spatial(elem) -> List[List[float]]:
    # ожидаем структуру .../entity_spatial/spatials_elements/spatial_element/ordinates/ordinate
    ords = elem.find('./entity_spatial/spatials_elements/spatial_element/ordinates')
    if ords is None:
        return []
    coords = _coords_from_ordinates(ords)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _extract_quarter_coords_from_block(root: ET.Element) -> List[List[float]]:
    """Извлекает координаты границы квартала непосредственно из секции cadastral_block/spatial_data.
    Возвращает список [x, y] или пустой список, если координаты не найдены.
    """
    # Приоритет 1: spatial_data - это граница квартала
    candidate_paths = [
        './cadastral_blocks/cadastral_block/spatial_data/entity_spatial/spatials_elements/spatial_element/ordinates',
        './cadastral_blocks/cadastral_block/spatial_data//ordinates',
        './cadastral_blocks/cadastral_block/entity_spatial/spatials_elements/spatial_element/ordinates',
        './cadastral_blocks/cadastral_block/contours/contour/entity_spatial/spatials_elements/spatial_element/ordinates',
        './cadastral_blocks/cadastral_block/contours_location/contours/contour/entity_spatial/spatials_elements/spatial_element/ordinates',
        './cadastral_blocks/cadastral_block/boundary/contour/entity_spatial/spatials_elements/spatial_element/ordinates',
    ]
    for path in candidate_paths:
        ords = root.find(path)
        if ords is None:
            continue
        coords = _coords_from_ordinates(ords)
        if coords:
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            print(f"✅ Найдены координаты границы квартала в XML: {len(coords)} точек (путь: {path})")
            return coords
    return []

def _add_rectangular_quarter(parcels_coords: List[List[List[float]]], quarters: List[Geometry], quarter_num: str | None):
    """Добавляет прямоугольный экстент квартала как fallback согласно правилам"""
    xs = [x for poly in parcels_coords for x, _ in poly]
    ys = [y for poly in parcels_coords for _, y in poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    quarters.append({
        "type": "LineString",
        "coordinates": [[min_x, max_y], [max_x, max_y], [max_x, min_y], [min_x, min_y], [min_x, max_y]],
        "properties": {
            "color": "#1E5AFF",  # Синий цвет согласно правилам
            "stroke-width": "0.3mm",  # Толщина 0.3мм согласно правилам
            "quarter_number": quarter_num or "unknown",
            "type": "rectangular_extent"
        }
    })
    print(f"✅ Создан прямоугольный экстент квартала (синий #1E5AFF, 0.3мм): X=[{min_x:.2f}, {max_x:.2f}], Y=[{min_y:.2f}, {max_y:.2f}]")


def parse_txt_polygon(path: str | Path) -> List[List[float]]:
    p = Path(path)
    if not p.exists():
        return []
    coords: List[List[float]] = []
    for line in p.read_text(encoding='utf-8').splitlines():
        s = line.strip()
        if not s:
            continue
        parts = s.split(';') if ';' in s else s.split()
        if len(parts) < 3:
            continue
        try:
            x = float(str(parts[1]).replace(',', '.'))
            y = float(str(parts[2]).replace(',', '.'))
            coords.append([x, y])
        except Exception:
            continue
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def parse_cadastre_xml(path: str | Path, default_crs: Dict[str, Any] | None = None) -> SRZUData:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"XML не найден: {p}")
    tree = ET.parse(str(p))
    root = tree.getroot()

    crs = default_crs or {"name": "LOCAL", "unit": "m"}
    crs_el = root.find('crs')
    if crs_el is not None:
        crs = {"name": crs_el.get('name') or crs.get('name'), "unit": crs_el.get('unit') or crs.get('unit')}

    target_parcels: List[Geometry] = []
    adjacent_parcels: List[Geometry] = []
    quarters: List[Geometry] = []
    admin_boundaries: List[Geometry] = []
    zones: List[Geometry] = []
    labels: List[Dict[str, Any]] = []

    # Квартал: номер и сбор всех земельных участков как смежников
    quarter_num = root.findtext('./cadastral_blocks/cadastral_block/cadastral_number')
    if quarter_num:
        print(f"🏘️ Найден кадастровый квартал: {quarter_num}")
        labels.append({"text": quarter_num, "x": 0.0, "y": 0.0, "kind": "quarter"})

    parcels_coords: List[List[List[float]]] = []
    for lr in root.findall('.//cadastral_blocks/cadastral_block/record_data/base_data/land_records/land_record'):
        poly = _polygon_from_spatial(lr.find('./contours_location/contours/contour'))
        if poly:
            parcels_coords.append(poly)
            
            # Извлекаем кадастровый номер участка
            cad_number = lr.findtext('./object/common_data/cad_number')
            
            adjacent_parcels.append({
                "type": "Polygon", "coordinates": [poly],
                "properties": {
                    "status": "EXISTING", 
                    "color": "#808080",
                    "cad_number": cad_number
                }
            })
            
            # Создаем подпись для участка (по центроиду)
            if cad_number and poly:
                cx, cy = _polygon_centroid(poly)
                # Форматируем номер: убираем префикс квартала для краткости (показываем только последнюю часть)
                short_number = cad_number.split(':')[-1] if ':' in cad_number else cad_number
                labels.append({
                    "text": f":{short_number}",
                    "x": cx,
                    "y": cy,
                    "kind": "parcel_label",
                    "full_number": cad_number
                })

    # Кадастровый квартал: сначала пытаемся взять напрямую из секции cadastral_block
    direct_quarter = _extract_quarter_coords_from_block(root)
    if direct_quarter:
        quarters.append({
            "type": "LineString",
            "coordinates": direct_quarter,
            "properties": {
                "color": "#1E5AFF",
                "stroke-width": "0.3mm",
                "quarter_number": quarter_num or "unknown",
                "source": "xml:cadastral_block"
            }
        })
        print("✅ Граница квартала прочитана напрямую из XML (cadastral_block)")
    # Если прямой геометрии нет — строим внешнюю границу как объединение всех полигонов
    # (строгое следование правилам: по внешним границам всех ЗУ)
    elif parcels_coords:
        print(f"🏘️ Построение границы квартала из {len(parcels_coords)} участков")
        print(f"📋 Согласно правилам: граница строится по внешним границам всех ЗУ в квартале")
        
        if Polygon is not None and unary_union is not None:
            # Используем shapely для точного построения границы
            polys = []
            for ring in parcels_coords:
                try:
                    polys.append(Polygon(ring))
                except Exception as e:
                    print(f"⚠️ Ошибка создания полигона: {e}")
                    continue
            
            if polys:
                try:
                    u = unary_union(polys)
                    if hasattr(u, 'geoms'):
                        # MultiPolygon - обрабатываем каждую часть
                        for i, geom in enumerate(u.geoms):
                            ext = list(geom.exterior.coords)
                            quarters.append({
                                "type": "LineString",
                                "coordinates": [[float(x), float(y)] for x, y in ext],
                                "properties": {
                                    "color": "#1E5AFF",  # Синий цвет согласно правилам
                                    "stroke-width": "0.3mm",  # Толщина 0.3мм согласно правилам
                                    "quarter_number": quarter_num or "unknown",
                                    "part": i + 1
                                }
                            })
                        print(f"✅ Граница квартала построена из {len(u.geoms)} частей (синий #1E5AFF, 0.3мм)")
                    else:
                        # Single Polygon
                        ext = list(u.exterior.coords)
                        quarters.append({
                            "type": "LineString",
                            "coordinates": [[float(x), float(y)] for x, y in ext],
                            "properties": {
                                "color": "#1E5AFF",  # Синий цвет согласно правилам
                                "stroke-width": "0.3mm",  # Толщина 0.3мм согласно правилам
                                "quarter_number": quarter_num or "unknown"
                            }
                        })
                        print(f"✅ Граница квартала построена как единый полигон (синий #1E5AFF, 0.3мм)")
                except Exception as e:
                    print(f"⚠️ Ошибка объединения полигонов: {e}")
                    # Fallback к прямоугольному экстенту
                    _add_rectangular_quarter(parcels_coords, quarters, quarter_num)
            else:
                print("⚠️ Не удалось создать полигоны из координат")
                _add_rectangular_quarter(parcels_coords, quarters, quarter_num)
        else:
            # Fallback — прямоугольный экстент
            print("⚠️ Shapely недоступен, используем прямоугольный экстент")
            _add_rectangular_quarter(parcels_coords, quarters, quarter_num)

    return {
        "crs": crs,
        "target_parcels": target_parcels,
        "adjacent_parcels": adjacent_parcels,
        "quarters": quarters,
        "admin_boundaries": admin_boundaries,
        "zones": zones,
        "labels": labels,
        # допустимые масштабы можно прокинуть из XML при наличии, иначе дефолт
        "allowed_scales": [1000, 500, 2000, 5000],
        "buffer_m": 200
    }


