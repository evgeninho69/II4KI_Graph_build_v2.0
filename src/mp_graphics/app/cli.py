import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..datasource.json_provider import load_cpp_data
from ..datasource.import_txt import parse_txt, parse_stations_txt
from ..datasource.import_xml import parse_xml
from ..datasource.import_xml_srzu import parse_cadastre_xml, parse_txt_polygon
from ..graphics.svg_generator import SVGConfig
from .html_graphics_pipeline import process_real_data_to_html


def _config_from_args(args: argparse.Namespace) -> SVGConfig:
    cfg = SVGConfig()
    # Формат листа
    fmt = (args.format or "A4").upper()
    if fmt == "A3":
        cfg.page_width_mm = 297.0
        cfg.page_height_mm = 420.0
    else:
        cfg.page_width_mm = 210.0
        cfg.page_height_mm = 297.0
    # DPI
    if args.dpi:
        cfg.dpi = int(args.dpi)
    return cfg


def _load_data(args: argparse.Namespace):
    if args.json:
        return load_cpp_data(Path(args.json))
    if args.txt:
        return parse_txt(Path(args.txt))
    if args.xml:
        return parse_xml(Path(args.xml))
    raise ValueError("Не указан источник данных (--json | --txt | --xml)")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="II4KI Graphics HTML/SVG-first — генератор листов")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", help="Путь к cpp JSON (contract)")
    group.add_argument("--txt", help="Путь к TXT координатам (демо)")
    group.add_argument("--xml", help="Путь к XML (демо)")
    parser.add_argument("--srzu-xml", help="Путь к XML выписке КПТ для SRZU", dest="srzu_xml")
    parser.add_argument("--srzu-txt", help="Путь к TXT с координатами целевого ЗУ для SRZU", dest="srzu_txt")
    parser.add_argument("--stations-txt", help="Путь к TXT со списком пунктов ОМС для SGP", dest="stations_txt")
    # По умолчанию выводим в корневую директорию проекта `out/`
    default_out = Path(__file__).resolve().parents[3] / "out"
    parser.add_argument("--out", required=False, default=str(default_out), help="Директория вывода (по умолчанию: <project>/out)")
    parser.add_argument("--format", choices=["A3", "A4"], default="A4", help="Формат листа (по умолчанию A4)")
    parser.add_argument("--dpi", type=int, default=96, help="DPI для конверсии мм→px (по умолчанию 96)")
    parser.add_argument("--sheets", nargs="*", choices=["SRZU", "SGP", "CH"], help="Ограничить генерацию выбранными листами")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cpp_data = _load_data(args)
    # При наличии SRZU‑XML — подмешиваем данные SRZU в общий пакет
    if args.srzu_xml:
        try:
            srzu_data = parse_cadastre_xml(Path(args.srzu_xml))
            # Если есть TXT с целевым участком — подмешиваем как target_parcels
            if args.srzu_txt:
                coords = parse_txt_polygon(Path(args.srzu_txt))
                if coords:
                    srzu_data.setdefault('target_parcels', []).append({
                        'type': 'Polygon',
                        'coordinates': [coords],
                        'properties': {'status': 'NEW', 'designation': ':ЗУ'}
                    })
            cpp_data['srzu'] = srzu_data
        except Exception as e:
            print(f"⚠️ Не удалось разобрать SRZU XML: {e}")
    cfg = _config_from_args(args)

    # Загружаем станции для SGP, если указан файл
    if args.stations_txt:
        try:
            stations = parse_stations_txt(Path(args.stations_txt))
            print(f"📡 Загружено {len(stations)} станций ОМС")
            # Добавляем станции в cpp_data
            if 'entities' not in cpp_data:
                cpp_data['entities'] = {}
            cpp_data['entities']['stations'] = stations
        except Exception as e:
            print(f"⚠️ Не удалось загрузить станции: {e}")

    # В текущей версии генерируем все листы; фильтрация по --sheets может быть добавлена на уровне пайплайна
    html_files = process_real_data_to_html(cpp_data, out_dir, config=cfg)

    print("Генерация завершена:")
    for k, v in html_files.items():
        print(f"  {k}: {v}")
    manifest = out_dir / "manifest.json"
    if manifest.exists():
        print(f"Манифест: {manifest}")
    
    # Обновляем сводку проекта
    _update_project_summary(out_dir, html_files)
    
    return 0


def _update_project_summary(out_dir: Path, html_files: Dict[str, Path]):
    """Обновляет сводку проекта с результатами генерации."""
    try:
        # Используем новый шаблон из public/templates
        template_path = Path(__file__).resolve().parents[3] / "public" / "templates" / "project_summary.html"
        summary_path = out_dir / "project_summary.html"
        
        if template_path.exists():
            # Копируем новый шаблон
            import shutil
            shutil.copy2(template_path, summary_path)
            
            # Обновляем содержимое шаблона
            with open(summary_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Обновляем заголовок с временной меткой
            from datetime import datetime
            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            content = content.replace(
                '<title>Межевой план — сводка</title>',
                f'<title>Межевой план — сводка (обновлено {timestamp})</title>'
            )
            
            # Обновляем список CH страниц
            ch_pages = [k for k in html_files.keys() if k.startswith('CH_p')]
            ch_pages_list = [html_files[ch_page].name for ch_page in sorted(ch_pages)]
            ch_script = f"window.__CH_LIST__ = {ch_pages_list};"
            content = content.replace(
                'let chPages = Array.isArray(window.__CH_LIST__) ? window.__CH_LIST__ : null;',
                f'{ch_script}\n      let chPages = Array.isArray(window.__CH_LIST__) ? window.__CH_LIST__ : null;'
            )
            
            # Сохраняем обновленный контент
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"📋 Сводка проекта обновлена: {summary_path}")
            
            # Автоматически открываем в браузере
            _open_browser(summary_path)
            
        else:
            print(f"⚠️ Шаблон сводки не найден: {template_path}")
    except Exception as e:
        print(f"⚠️ Ошибка обновления сводки: {e}")


def _open_browser(file_path: Path):
    """Автоматически открывает файл в браузере по умолчанию."""
    try:
        import webbrowser
        import sys
        import platform
        
        # Преобразуем путь в URL
        if platform.system() == "Windows":
            url = f"file:///{file_path.as_posix()}"
        else:
            url = f"file://{file_path.absolute()}"
        
        # Открываем в браузере по умолчанию
        webbrowser.open(url)
        print(f"🌐 Сводка проекта открыта в браузере")
        
    except Exception as e:
        print(f"⚠️ Не удалось открыть браузер: {e}")
        print(f"💡 Откройте файл вручную: {file_path}")


if __name__ == "__main__":
    raise SystemExit(main())


