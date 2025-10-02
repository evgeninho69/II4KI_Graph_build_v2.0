from pathlib import Path
import math

from ..datasource.json_provider import load_cpp_data
from ..graphics.svg_generator import SVGGraphicsGenerator, SVGConfig
from ..exporters.html_publisher import generate_html_sheet


HTML_STYLE = """
  <style>
    :root{ --page-w:210mm; --page-h:297mm; --frame:14mm; --line:#000 }
    html,body{height:100%; background:#f3f3f3}
    body{margin:20px; font:13px/1.35 'Times New Roman', Times, serif; color:#111}
    .sheet{width:var(--page-w); height:var(--page-h); background:#fff; margin:0 auto; box-shadow:0 4px 24px rgba(0,0,0,.18); position:relative; border:1px solid var(--line)}
    .header{position:absolute; left:var(--frame); right:var(--frame); top:var(--frame); height:18mm; border:1px solid var(--line); border-bottom:none; display:flex; align-items:center; justify-content:center; font-weight:700}
    .workarea{position:absolute; left:var(--frame); right:var(--frame); top:calc(var(--frame) + 18mm); bottom:calc(var(--frame) + 40mm); border:1px solid var(--line); background:#fff; overflow:hidden}
    .legend{position:absolute; left:var(--frame); right:var(--frame); bottom:var(--frame); height:40mm; border:1px solid var(--line); padding:6mm 10mm; overflow:hidden}
    .legend h3{margin:0 0 6px 0; font-weight:700}
    .row{display:flex; align-items:center; gap:16px; margin:6px 0}
    .sym-col{width:120px; display:flex; align-items:center; justify-content:center}
    .sym-col.col-v{flex-direction:column}
    .desc{flex:1}
    .line-sample{width:46px; height:2px; background:#f00}
    .line-sample.black{background:#000}
    .dot{width:6px; height:6px; border-radius:50%; background:#000}
    .dot-red{width:6px; height:6px; border-radius:50%; background:#f00}
    .tri{width:0;height:0;border-left:8px solid transparent;border-right:8px solid transparent;border-bottom:14px solid #f00; position:relative}
    .tri .center{position:absolute; left:50%; top:58%; width:5px; height:5px; background:#f00; border-radius:50%; transform:translate(-50%,-50%)}
    .dist{display:flex; flex-direction:column; align-items:flex-start; line-height:1}
    .dist .val{font-size:16px; letter-spacing:2px}
    .dist .unit{font-size:12px}
    .arrow-right{width:80px; height:0; border-top:2px solid #666; position:relative}
    .arrow-right:after{content:""; position:absolute; right:-2px; top:-6px; border-left:8px solid #666; border-top:6px solid transparent; border-bottom:6px solid transparent}
  </style>
"""


def legend_row(symbol_html: str, description_html: str) -> str:
    return f'<div class="row"><div class="sym-col">{symbol_html}</div><div class="desc">{description_html}</div></div>'


def build_sgp_legend_html(has_stations: bool, has_dirs: bool, has_vertices: bool, sample_station_name: str = "ОМС") -> str:
    rows = []
    # 1) Вновь образованная часть границы
    rows.append(legend_row('<div class="line-sample"></div>', 'Вновь образованная часть границы, сведения о которой достаточны для определения ее местоположения'))
    # 2) Значение расстояния по направлению
    if has_dirs and has_stations:
        rows.append(legend_row('<div class="dist"><span class="val">62,77</span><span class="unit">м</span></div>', 'Значение расстояния по направлению от пункта ГГС/ОМС/ТСО до характерной поворотной точки, в метрах'))
    # 3) Пункт ОМС/ГГС и его название
    if has_stations:
        tri = '<div class="tri"><div class="center"></div></div><div style="margin-top:6px; font-weight:700;">' + sample_station_name + '</div>'
        rows.append(legend_row(f'<div class="sym-col col-v">{tri}</div>', 'Пункт опорной межевой сети и его название'))
    # 4) Направление от пункта до характерной точки
    if has_stations:
        rows.append(legend_row('<div class="arrow-right"></div>', 'Направление от пункта ГГС/ОМС/ТСО до характерной поворотной точки'))
    # 5) Характерная точка границы
    if has_vertices:
        rows.append(legend_row('<div class="dot"></div>', 'Характерная точка границы, сведения о которой позволяют однозначно определить ее положение на местности'))
    return "\n".join(rows)


def centroid(points):
    x = sum(p[0] for p in points) / len(points)
    y = sum(p[1] for p in points) / len(points)
    return (x, y)


def build_sgp_svg(parcel_points, stations):
    # SVG canvas
    width, height = 800, 600

    # Центр экрана
    cx, cy = width / 2, height / 2

    # Центр полигона
    cpx, cpy = centroid(parcel_points)

    # Нормализация полигона к ~300 px ширины
    min_x = min(p[0] for p in parcel_points)
    max_x = max(p[0] for p in parcel_points)
    min_y = min(p[1] for p in parcel_points)
    max_y = max(p[1] for p in parcel_points)
    w = max_x - min_x
    h = max_y - min_y
    scale = 300.0 / max(w, h) if max(w, h) else 1.0

    def to_svg(x, y):
        # перенос к центру, ось Y вниз
        sx = cx + (x - cpx) * scale
        sy = cy - (y - cpy) * scale
        return sx, sy

    # Полигон ЗУ (красный контур)
    poly_svg = [to_svg(x, y) for x, y in parcel_points]
    points_attr = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly_svg)
    svg_parts = [f'<polygon points="{points_attr}" fill="none" stroke="#FF0000" stroke-width="1.2"/>']
    # Внешние подписи вершин (н1..нN): выносим наружу от контура и разводим буфером
    cx_svg = sum(p[0] for p in poly_svg) / len(poly_svg)
    cy_svg = sum(p[1] for p in poly_svg) / len(poly_svg)
    label_boxes = []
    def place_outside(px, py, text, base_r=14, fs=12):
        w = max(18.0, 0.6*fs*len(text))
        h = fs*1.2
        vx, vy = px - cx_svg, py - cy_svg
        norm = math.hypot(vx, vy) or 1.0
        ux, uy = vx / norm, vy / norm
        r = base_r
        for _ in range(12):
            x = px + ux * r
            y = py + uy * r
            x1, y1, x2, y2 = x - w/2, y - h, x + w/2, y
            if all(x2 < a1 or x1 > a3 or y2 < a2 or y1 > a4 for a1,a2,a3,a4 in label_boxes):
                label_boxes.append((x1,y1,x2,y2))
                return x, y, fs
            r += 6
        label_boxes.append((px-w/2, py-h-2, px+w/2, py-2))
        return px, py-2, fs
    # если контур замкнут (последняя точка совпадает с первой), последнюю подпись не выводим
    total_vertices = len(poly_svg)
    is_closed = total_vertices > 2 and abs(poly_svg[0][0] - poly_svg[-1][0]) < 1e-6 and abs(poly_svg[0][1] - poly_svg[-1][1]) < 1e-6
    draw_vertices = poly_svg[:-1] if is_closed else poly_svg
    for idx,(x,y) in enumerate(draw_vertices, start=1):
        svg_parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" fill="#f00" />')
        tx,ty,fs=place_outside(x,y,f"н{idx}")
        svg_parts.append(f'<text x="{tx:.2f}" y="{ty:.2f}" fill="#000" stroke="#fff" stroke-width="0.8" paint-order="stroke" font-size="{fs}" font-family="Times New Roman, serif">н{idx}</text>')

    # Схематическое размещение пунктов: радиальная компрессия (подбираем, чтобы все поместились)
    init_compress = 0.25
    margin = 40  # пикселей до краёв области
    label_pad = 30  # добавочный запас под подпись треугольника

    # подготовить список вершин в исходных координатах
    vertices_src = parcel_points

    # подобрать общий коэффициент сжатия так, чтобы все пункты попадали в рабочее поле
    if stations:
        # максимально допустимый коэффициент, чтобы все сжатые точки оказались внутри рабочей области
        half_w = width/2 - (margin + label_pad)
        half_h = height/2 - (margin + label_pad)
        max_factor = init_compress
        for st in stations:
            vx, vy = st['x'] - cpx, st['y'] - cpy
            if abs(vx)>1e-9:
                fx = (half_w/scale)/abs(vx)
                max_factor = min(max_factor, fx)
            if abs(vy)>1e-9:
                fy = (half_h/scale)/abs(vy)
                max_factor = min(max_factor, fy)
        compress = max(0.05, min(init_compress, max_factor))
    else:
        compress = init_compress

    # выбрать одну общую вершину ЗУ для всех направлений: минимальная сумма расстояний до всех пунктов
    if stations:
        best_idx = 0
        best_sum = 1e30
        for i, (vx0, vy0) in enumerate(vertices_src):
            s = 0.0
            for st in stations:
                s += math.hypot(st['x'] - vx0, st['y'] - vy0)
            if s < best_sum:
                best_sum = s
                best_idx = i
        common_vertex = vertices_src[best_idx]
        common_vertex_svg = to_svg(*common_vertex)
    else:
        common_vertex = (cpx, cpy)
        common_vertex_svg = to_svg(cpx, cpy)

    for st in stations:
        sx_src, sy_src = st['x'], st['y']
        # сжатая позиция пункта
        vx_c, vy_c = cpx + (sx_src - cpx) * compress, cpy + (sy_src - cpy) * compress
        x1, y1 = common_vertex_svg
        x2, y2 = to_svg(vx_c, vy_c)
        # гарантированно вписываем пункт в рабочую область
        x2 = max(margin, min(width - margin, x2))
        y2 = max(margin, min(height - margin, y2))
        # направление от общей вершины к пункту
        svg_parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#666" stroke-width="1"/>')
        # расстояние от пункта до общей вершины (реальное)
        dist = math.hypot(sx_src - common_vertex[0], sy_src - common_vertex[1])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        # подложка под длину
        fs = 12
        tw = 0.6*fs*len(f"{dist:.1f} м")
        th = fs*1.2
        svg_parts.append(f'<g transform="rotate({ang:.2f} {mx:.2f} {my:.2f})">'
                         f'<rect x="{mx - tw/2:.2f}" y="{my - th + 2:.2f}" width="{tw:.2f}" height="{th:.2f}" fill="#fff" opacity="0.85" />'
                         f'<text x="{mx:.2f}" y="{my:.2f}" fill="#000" font-size="{fs}" font-family="Times New Roman, serif" text-anchor="middle">{dist:.1f} м</text>'
                         f'</g>')
        # знак пункта (красный треугольник с белой заливкой и красной точкой)
        svg_parts.append(f'<path d="M {x2:.2f} {y2-8:.2f} l 6 10 l -12 0 Z" fill="#fff" stroke="#f00" stroke-width="2"/>')
        svg_parts.append(f'<circle cx="{x2:.2f}" cy="{y2-2:.2f}" r="1.8" fill="#f00"/>')
        # подпись пункта: смещаем от символа вдоль луча, чтобы не накладывалась на треугольник
        label = st.get('code') or st.get('name', '')
        fsn = 12
        dx, dy = x2 - x1, y2 - y1
        dlen = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dlen, dy / dlen
        lx, ly = x2 + ux * 16, y2 + uy * 16
        lw = 0.6*fsn*len(label)
        lh = fsn*1.2
        svg_parts.append(f'<text x="{lx:.2f}" y="{ly:.2f}" fill="#000" font-size="{fsn}" font-family="Times New Roman, serif" text-anchor="middle">{label}</text>')

    svg = f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">' + "\n".join(svg_parts) + '</svg>'
    return svg


def generate_sgp_sheet(input_dir: Path, output_path: Path):
    # Загружаем cpp_data из JSON-контракта
    data_file = input_dir / 'real_data_cpp.json'
    cpp_data = load_cpp_data(data_file)

    # Генерируем SVG через общий генератор, раздел SGP
    generator = SVGGraphicsGenerator(SVGConfig(width=800, height=600))
    svg = generator.generate_complete_svg(cpp_data, 'SGP')

    # Легенда формируется в html_publisher через tokens; здесь можно собрать через общий helper
    from ..graphics.svg_generator import generate_legend_for_data
    legend_items = generate_legend_for_data(cpp_data)

    # Сформировать HTML через общий publisher и шаблон листа
    generate_html_sheet(
        drawing_svg=svg,
        legend_items=legend_items,
        title='Схема геодезических построений',
        scale=f"Масштаб 1:{(cpp_data.get('scales_allowed') or [500])[0]}",
        output_path=str(output_path)
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[4]
    input_dir = root / 'docs' / 'МП' / 'test'
    out = root / 'out_html' / 'SGP.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_sgp_sheet(input_dir, out)


