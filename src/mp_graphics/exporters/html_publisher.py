import os
from pathlib import Path

# Окончательно правильный путь: три уровня вверх
TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "public" / "templates" / "sheet_template.html"


def generate_html_sheet(drawing_svg: str, legend_items: list, title: str, scale: str, output_path: str):
    """
    Формирует HTML-лист: вставляет SVG-графику и легенду в шаблон, сохраняет результат.
    drawing_svg: SVG-код для вставки в рабочую область
    legend_items: список словарей {symbol, text}
    title: заголовок листа
    scale: строка масштаба (например, 'Масштаб 1:500')
    output_path: путь для сохранения итогового HTML
    """
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()
    # CSS уже подключен в шаблоне, инъекция не требуется

    # Подмена заголовка по идентификатору header.header
    html = html.replace(
        '<header class="header" aria-label="Заголовок листа">\n      Чертеж земельных участков и их частей\n    </header>',
        f'<header class="header" aria-label="Заголовок листа">{title or "Чертеж земельных участков и их частей"}</header>'
    )
    # Подмена масштаба по классу .scale
    html = html.replace(
        '<div class="scale">Масштаб 1:500</div>',
        f'<div class="scale">{scale}</div>'
    )
    # Вставка SVG-графики по id drawingArea
    html = html.replace(
        '<main id="drawingArea" class="workarea" aria-label="Поле чертежа (пустое)"></main>',
        f'<main id="drawingArea" class="workarea">{drawing_svg}</main>'
    )
    # Формирование легенды (новый формат: {css,text})
    # Поддержка старого формата сохраняется выше по коду
    def render_item(it):
        css = it.get("css") or f"legend-{it.get('symbol')}"
        text = it.get("text", "")
        return f'<div class="legend-item"><div class="legend-symbol"><div class="{css}"></div></div><span>— {text}</span></div>'
    legend_html = "<strong>Условные обозначения:</strong><br>" + "\n".join(render_item(it) for it in legend_items)
    html = html.replace(
        '<aside id="legendArea" class="legend" aria-label="Условные обозначения">\n      Условные обозначения:\n    </aside>',
        f'<aside id="legendArea" class="legend">{legend_html}</aside>'
    )
    # Сохраняем итоговый HTML
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

# Пример использования
if __name__ == "__main__":
    # Пример SVG-графики (можно заменить на реальную)
    svg = '<svg width="100%" height="100%" viewBox="0 0 100 100"><rect x="10" y="10" width="80" height="80" fill="#e0e0e0" stroke="#333"/><circle cx="50" cy="50" r="30" fill="none" stroke="#0077cc" stroke-width="2"/></svg>'
    legend = [
        {"symbol": "●", "text": "Образуемая точка"},
        {"symbol": "—", "text": "Часть границы"}
    ]
    generate_html_sheet(svg, legend, "Чертеж земельных участков и их частей", "Масштаб 1:500", "out/result.html")
