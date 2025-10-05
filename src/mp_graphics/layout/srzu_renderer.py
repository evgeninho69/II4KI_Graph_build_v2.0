from __future__ import annotations

from typing import Dict, Any, List, Tuple, Set

from ..datasource.json_contract import SRZUData, Geometry
from ..graphics.svg_generator import SVGConfig
from ..core.units import mm_to_px
from ..core.page import choose_format_and_scale, PageFormat
from ..graphics.label_place import place_label


def _collect_coords(geoms: List[Geometry]) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for g in geoms or []:
        gtype = g.get("type")
        coords = g.get("coordinates") or []
        if gtype == "Polygon":
            ring = coords[0] if coords else []
            for x, y in ring:
                pts.append((x, y))
        elif gtype == "MultiPolygon":
            for poly in coords:
                ring = poly[0] if poly else []
                for x, y in ring:
                    pts.append((x, y))
        elif gtype == "LineString":
            for x, y in coords:
                pts.append((x, y))
    return pts


def _bbox(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    if not points:
        return (0.0, 0.0, 1.0, 1.0)
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    return (min_x, min_y, max_x, max_y)


def _to_px(x: float, y: float, center: Tuple[float, float], scale: float, cfg: SVGConfig) -> Tuple[float, float]:
    cx, cy = center
    px = (x - cx) * scale + cfg.width / 2.0
    py = (y - cy) * scale + cfg.height / 2.0
    return px, py


def _poly_to_svg_points(coords: List[List[float]], center, scale, cfg: SVGConfig) -> str:
    pts = []
    for x, y in coords:
        px, py = _to_px(float(x), float(y), center, scale, cfg)
        pts.append(f"{px:.2f},{py:.2f}")
    return " ".join(pts)


def _polygon_centroid(coords: List[List[float]]) -> Tuple[float, float]:
    # coords: list of [x,y], предполагаем замкнутый контур
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


def _is_zone_legible(scale_den: int, cfg: SVGConfig) -> bool:
    # Критерий: при слишком мелком масштабе (например > 1:2000) скрываем зоны
    # Шрифт: обеспечивается min_font_pt на стороне текста, но при 1:>2000 часто карта перегружена
    return scale_den <= 2000


def render_srzu(data: SRZUData, cfg: SVGConfig) -> str | Tuple[str, Set[str]]:
    # Создаем буферную зону вокруг основного ЗУ для увеличения масштаба
    target_parcels = data.get("target_parcels", [])
    target_pts = _collect_coords(target_parcels)
    
    if target_pts:
        # Находим центр основного ЗУ
        target_min_x, target_min_y, target_max_x, target_max_y = _bbox(target_pts)
        target_center_x = (target_min_x + target_max_x) / 2
        target_center_y = (target_min_y + target_max_y) / 2
        
        # Создаем буферную зону вокруг основного ЗУ (увеличенный радиус для лучшего масштаба)
        buffer_radius = 300.0  # Увеличиваем радиус для более крупного масштаба
        print(f"🎯 Создание буферной зоны радиусом {buffer_radius} м вокруг основного ЗУ")
        print(f"📍 Центр основного ЗУ: X={target_center_x:.2f}, Y={target_center_y:.2f}")
        
        # Фильтруем смежные участки по буферной зоне
        adjacent_parcels = data.get("adjacent_parcels", [])
        filtered_adjacent = []
        
        for parcel in adjacent_parcels:
            parcel_coords = _collect_coords([parcel])
            if parcel_coords:
                parcel_center_x = sum(x for x, y in parcel_coords) / len(parcel_coords)
                parcel_center_y = sum(y for x, y in parcel_coords) / len(parcel_coords)
                
                # Проверяем, попадает ли участок в буферную зону
                distance = ((parcel_center_x - target_center_x) ** 2 + (parcel_center_y - target_center_y) ** 2) ** 0.5
                if distance <= buffer_radius:
                    filtered_adjacent.append(parcel)
        
        print(f"📊 Фильтрация участков: {len(adjacent_parcels)} → {len(filtered_adjacent)} (в буферной зоне)")
        
        # Обновляем данные с отфильтрованными участками
        data = data.copy()
        data["adjacent_parcels"] = filtered_adjacent
        
        # Собираем bbox только по отфильтрованным данным
        all_pts = []
        for layer in (target_parcels, filtered_adjacent, data.get("quarters", [])):
            all_pts.extend(_collect_coords(layer))
        
        # Создаем bbox на основе буферной зоны
        min_x = target_center_x - buffer_radius
        min_y = target_center_y - buffer_radius
        max_x = target_center_x + buffer_radius
        max_y = target_center_y + buffer_radius
        
        print(f"🎯 Буферная зона: X=[{min_x:.2f}, {max_x:.2f}], Y=[{min_y:.2f}, {max_y:.2f}]")
    else:
        # Fallback к обычной логике
        all_pts = []
        for layer in (data.get("target_parcels", []), data.get("adjacent_parcels", []), data.get("quarters", [])):
            all_pts.extend(_collect_coords(layer))
        min_x, min_y, max_x, max_y = _bbox(all_pts)
        buf_m = float(data.get("buffer_m", 200))
        min_x -= buf_m; min_y -= buf_m; max_x += buf_m; max_y += buf_m
    
    # Добавляем небольшой отступ под подписи
    pad_x = (max_x - min_x) * 0.05 if (max_x > min_x) else 1.0
    pad_y = (max_y - min_y) * 0.05 if (max_y > min_y) else 1.0
    content_bbox = (min_x - pad_x, min_y - pad_y, max_x + pad_x, max_y + pad_y)

    # Выбор формата и масштаба (A4→A3), масштаб как 1:N
    # Принудительно используем более крупный масштаб для буферной зоны
    allowed_scales = [500, 250, 1000, 2000]  # Приоритет крупным масштабам
    page_fmt, scale_den = choose_format_and_scale(content_bbox, allowed_scales=allowed_scales, min_font_pt=cfg.min_font_pt, dpi=cfg.dpi)
    print(f"📐 Выбран масштаб 1:{scale_den} для буферной зоны")

    # Устанавливаем размеры страницы под формат
    cfg.page_width_mm = page_fmt.width_mm
    cfg.page_height_mm = page_fmt.height_mm
    cfg.margin_mm = max(cfg.margin_mm, 10.0)

    # Пересчёт пиксельных размеров полотна
    cfg.width = int(mm_to_px(cfg.page_width_mm, cfg.dpi))
    cfg.height = int(mm_to_px(cfg.page_height_mm, cfg.dpi))

    # Вычислим scale (px/метр) исходя из подобранного N: 1 мм на листе = N мм на местности => 1 px ~ 25.4/dpi мм
    mm_per_px = 25.4 / float(cfg.dpi)
    m_per_px = (scale_den * mm_per_px) / 1000.0
    scale = 1.0 / max(1e-9, m_per_px)

    # Рабочая область и оффсеты
    ox = mm_to_px(page_fmt.margin_left_mm, cfg.dpi)
    oy = mm_to_px(page_fmt.margin_top_mm, cfg.dpi)
    work_w = mm_to_px(page_fmt.workarea_width_mm, cfg.dpi)
    work_h = mm_to_px(page_fmt.workarea_height_mm, cfg.dpi)

    cx = (content_bbox[0] + content_bbox[2]) / 2.0
    cy = (content_bbox[1] + content_bbox[3]) / 2.0
    center = (cx, cy)

    parts: List[str] = [f'<svg width="{cfg.width}" height="{cfg.height}" viewBox="0 0 {cfg.width} {cfg.height}" xmlns="http://www.w3.org/2000/svg">']
    # clipPath рабочей области
    parts.append(f'<defs><clipPath id="workarea"><rect x="{ox:.2f}" y="{oy:.2f}" width="{work_w:.2f}" height="{work_h:.2f}"/></clipPath></defs>')
    parts.append('<g clip-path="url(#workarea)">')
    used_tokens: Set[str] = set()

    # Локальные преобразования координат в пиксели относительно центра рабочей области
    def to_px_local(x: float, y: float) -> Tuple[float, float]:
        px = (x - cx) * scale + ox + work_w / 2.0
        py = (y - cy) * scale + oy + work_h / 2.0
        return px, py

    def poly_points_local(coords: List[List[float]]) -> str:
        pts = []
        for x, y in coords:
            px, py = to_px_local(float(x), float(y))
            pts.append(f"{px:.2f},{py:.2f}")
        return " "+" ".join(pts)

    # QUARTERS (синие линии) - граница квартала
    quarter_polylines: List[List[Tuple[float, float]]] = []
    admin_polylines: List[List[Tuple[float, float]]] = []
    quarters_drawn = 0
    
    # Собираем подписи кварталов
    quarter_labels: List[Dict[str, Any]] = []
    for g in data.get("quarters", []) or []:
        if g.get("type") != "LineString":
            continue
        coords = g.get("coordinates") or []
        if not coords:
            continue
            
        # Получаем свойства для стилизации
        props = g.get("properties", {})
        color = props.get("color", "#1E5AFF")
        stroke_width = props.get("stroke-width", "0.5mm")
        quarter_number = props.get("quarter_number", "")
        quarter_type = props.get("type", "boundary")
        
        pts_attr = poly_points_local(coords)
        
        # Стилизация в зависимости от типа границы
        if not stroke_width:
            stroke_width = "0.3mm"
        if quarter_type == "rectangular_extent":
            # Пунктирная линия для прямоугольного экстента
            parts.append(f'<polyline points="{pts_attr}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-dasharray="2,1" opacity="0.8"/>')
        else:
            # Сплошная линия для точной границы
            parts.append(f'<polyline points="{pts_attr}" fill="none" stroke="{color}" stroke-width="{stroke_width}"/>')
        
        # накапливаем в пикселях для избегания пересечений выносок
        poly_px: List[Tuple[float, float]] = []
        for x, y in coords:
            px, py = to_px_local(float(x), float(y))
            poly_px.append((px, py))
        quarter_polylines.append(poly_px)
        quarters_drawn += 1
        
        # Добавляем подпись квартала в центре границы
        if quarter_number and coords:
            # Находим центр границы в исходных координатах (метрах)
            center_x = sum(float(x) for x, y in coords) / len(coords)
            center_y = sum(float(y) for x, y in coords) / len(coords)
            
            # Добавляем подпись квартала (только номер, без слова "Квартал")
            quarter_labels.append({
                "text": quarter_number,  # Только кадастровый номер
                "x": center_x,  # Координаты в метрах, преобразуются позже
                "y": center_y,
                "kind": "quarter_label"
            })

    # ADMIN boundaries (чёрные тонкие)
    admin_drawn = 0
    for g in data.get("admin_boundaries", []) or []:
        if g.get("type") != "LineString":
            continue
        coords = g.get("coordinates") or []
        pts_attr = poly_points_local(coords)
        parts.append(f'<polyline points="{pts_attr}" fill="none" stroke="#000000" stroke-width="0.2mm"/>')
        admin_drawn += 1
        poly_px: List[Tuple[float, float]] = []
        for x, y in coords:
            px, py = to_px_local(float(x), float(y))
            poly_px.append((px, py))
        admin_polylines.append(poly_px)

    # ZONES (зелёные контуры) — фильтрация по читаемости
    zones_drawn = 0
    if _is_zone_legible(scale_den, cfg):
        for g in data.get("zones", []) or []:
            if g.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            color = "#00AA00"
            width_m = float(g.get("properties", {}).get("width_m", 0) or 0)
            if g.get("type") == "Polygon":
                ring = (g.get("coordinates") or [[]])[0]
                pts_attr = poly_points_local(ring)
                parts.append(f'<polygon points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm"/>')
                zones_drawn += 1
                # коридор — две параллельные, если задана ширина
                if width_m > 0:
                    offset_px = (width_m / 2.0) * scale
                    parts.append(f'<polyline points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm" transform="translate(0,{offset_px:.2f})"/>')
                    parts.append(f'<polyline points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm" transform="translate(0,{-offset_px:.2f})"/>')
            else:
                for poly in g.get("coordinates") or []:
                    ring = (poly or [[]])[0]
                    pts_attr = poly_points_local(ring)
                    parts.append(f'<polygon points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm"/>')
                    zones_drawn += 1
    if zones_drawn > 0:
        used_tokens.add("zone")

    # ADJACENT parcels (серые контуры)
    adjacent_drawn = 0
    for g in data.get("adjacent_parcels", []) or []:
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        color = g.get("properties", {}).get("color", "#808080")
        if g.get("type") == "Polygon":
            ring = (g.get("coordinates") or [[]])[0]
            pts_attr = poly_points_local(ring)
            parts.append(f'<polygon points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm"/>')
        else:
            for poly in g.get("coordinates") or []:
                ring = (poly or [[]])[0]
                pts_attr = poly_points_local(ring)
                parts.append(f'<polygon points="{pts_attr}" fill="none" stroke="{color}" stroke-width="0.2mm"/>')
        adjacent_drawn += 1

    # TARGET parcels - рисуем по сегментам с правильными цветами для СРЗУ
    target_drawn = 0
    for g in data.get("target_parcels", []) or []:
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        
        # Для СРЗУ рисуем границы по сегментам с разными цветами
        # По умолчанию считаем все границы новыми (красными) для целевого участка
        ring = None
        if g.get("type") == "Polygon":
            ring = (g.get("coordinates") or [[]])[0]
        else:
            # MultiPolygon - берем первый полигон
            ring = (g.get("coordinates") or [[]])[0][0] if g.get("coordinates") else []
        
        if ring and len(ring) >= 3:
            # Рисуем каждый сегмент границы отдельно
            for i in range(len(ring)):
                j = (i + 1) % len(ring)
                x1, y1 = ring[i]
                x2, y2 = ring[j]
                
                # Преобразуем координаты в пиксели
                px1, py1 = to_px_local(x1, y1)
                px2, py2 = to_px_local(x2, y2)
                
                # Для целевого участка на СРЗУ: все границы красные (новые)
                # В будущем здесь можно добавить логику определения статуса сегмента
                stroke = "#ff0000"  # Красный для новых границ целевого участка
                legend_token = "target"
                
                # Рисуем сегмент с правильной толщиной согласно правилам СРЗУ
                parts.append(f'<line x1="{px1:.2f}" y1="{py1:.2f}" x2="{px2:.2f}" y2="{py2:.2f}" stroke="{stroke}" stroke-width="0.2mm"/>')
                used_tokens.add(legend_token)
        
        target_drawn += 1

    # LABELS: размещение с выносками и избеганием пересечений
    labels = list(data.get("labels", []) or [])
    
    # Добавляем подписи кварталов
    labels.extend(quarter_labels)
    # Если нет явной подписи parcel — сгенерируем по центроиду первого target
    if not any((l.get("kind") == "parcel") for l in labels):
        if (data.get("target_parcels") or []) and (data.get("target_parcels")[0].get("type") == "Polygon"):
            ring = (data.get("target_parcels")[0].get("coordinates") or [[]])[0]
            cx0, cy0 = _polygon_centroid(ring)
            designation = data.get("target_parcels")[0].get("properties", {}).get("designation") or ":ЗУ"
            labels.append({"text": designation, "x": cx0, "y": cy0, "kind": "parcel"})

    avoid = quarter_polylines + admin_polylines
    for lbl in labels:
        try:
            x = float(lbl.get("x", 0))
            y = float(lbl.get("y", 0))
        except Exception:
            continue
        ax, ay = to_px_local(x, y)
        text = str(lbl.get("text", ""))
        # Увеличенный размер для номера квартала
        kind = (lbl.get("kind") or "").lower()
        # Динамический размер шрифта по масштабу (1:N)
        def font_px_for_scale(n: int) -> int:
            if n <= 500: return 16
            if n <= 1000: return 14
            if n <= 2000: return 12
            return 11
        fs_px = max(cfg.font_size, font_px_for_scale(scale_den))
        if kind == "quarter":
            fs_px = max(fs_px, int(round(18 * (cfg.dpi / 72.0))))
        
        # Для подписей участков используем prefer_center=True (размещаем в центре без выноски)
        prefer_center = (kind == "parcel_label")
        lx, ly, leader = place_label((ax, ay), text, avoid, dpi=cfg.dpi, font_size_px=fs_px, min_font_pt=cfg.min_font_pt, prefer_center=prefer_center)
        color = "#000000"
        
        if kind == "quarter":
            color = "#1E5AFF"
            used_tokens.add("label-quarter")
        elif kind == "quarter_label":
            color = "#1E5AFF"
            # Крупный синий шрифт для номера квартала (18-22pt)
            fs_px = max(fs_px, int(round(20 * (cfg.dpi / 72.0))))
            used_tokens.add("label-quarter")
        elif kind == "parcel_label":
            # Подписи кадастровых номеров участков
            color = "#000000"
            fs_px = max(8, int(round(10 * (cfg.dpi / 72.0))))  # Меньший размер для номеров участков
            used_tokens.add("label-parcel")
        elif kind == "zone":
            color = "#00AA00"
        elif kind == "parcel":
            used_tokens.add("label-parcel")
        if leader:
            parts.append(leader)
        parts.append(f'<text x="{lx:.2f}" y="{ly:.2f}" fill="{color}" font-size="{fs_px}" font-family="{cfg.font_family}" text-anchor="start">{text}</text>')

    # Титульная полоса и масштаб
    title = "Схема расположения земельных участков"
    scale_txt = f"Масштаб 1:{scale_den}"
    parts.append('</g>')
    parts.append('</svg>')
    # Токены SRZU слоёв
    if target_drawn > 0:
        used_tokens.add("target")
    if adjacent_drawn > 0:
        used_tokens.add("adjacent")
    if quarters_drawn > 0:
        used_tokens.add("quarters")
    if admin_drawn > 0:
        used_tokens.add("admin")

    svg = "\n".join(parts)
    # Возвращаем svg и использованные токены (для легенды)
    return svg, used_tokens


