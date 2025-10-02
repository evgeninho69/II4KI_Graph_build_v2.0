# II4KI Graphics (HTML/SVG-first)

## Структура
- `src/mp_graphics/app`: входы и пайплайн (html_graphics_pipeline.py, sgp_generator.py)
- `src/mp_graphics/graphics`: генерация SVG (svg_generator.py)
- `src/mp_graphics/exporters`: публикация HTML (html_publisher.py)
- `src/mp_graphics/layout`: билдеры схем (scheme_layout_builder.py)
- `src/mp_graphics/core`: типы/константы/валидация (заполнить при рефакторинге)
- `src/mp_graphics/datasource`: PostgreSQL и импорт TXT/XML (добавить)
- `public/templates`: шаблоны листов (sheet_template.html, project_summary.html)
- `public/css`: стили
- `tests/snapshots`: снапшоты SVG/HTML

## Быстрый старт
1) Создайте venv и установите зависимости (через `pyproject.toml` или `requirements.txt`).
2) Запустите скрипты из `src/mp_graphics/app/` для генерации листов.
3) Результат: HTML-листы в корне проекта или в указанной директории вывода.

## Заметки
- Все импорты должны быть относительно `src/mp_graphics`.
- HTML/SVG-first: никакой DXF/PDF/растр в кодовой базе (конверсия в PDF — вне пайплайна).

## CLI

Пример запуска пайплайна:

```bash
python -m mp_graphics.app.cli --json docs/МП/real_data_cpp.json --out out_html --format A4 --dpi 96
```

На выходе будут сгенерированы:
- `SRZU.html`, `SGP.html`, `CH_pN.html`
- `manifest.json` с перечнем листов
