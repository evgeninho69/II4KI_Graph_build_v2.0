"""
Полный пайплайн для генерации HTML-листов межевого плана
Интегрирует все этапы: от обработки данных до генерации HTML с SVG-графикой
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, List

from ..graphics.svg_generator import SVGGraphicsGenerator, SVGConfig, generate_legend_for_data
from ..exporters.html_publisher import generate_html_sheet
from ..datasource.json_provider import load_cpp_data
from ..graphics.labels import ParcelLabelFormatter, validate_label
from ..core.enums import OperationType
from ..layout.srzu_renderer import render_srzu


def process_real_data_to_html(cpp_data: Dict[str, Any], 
                            output_dir: Path,
                            config: SVGConfig = None) -> Dict[str, Path]:
    """
    Полный пайплайн обработки реальных данных в HTML-листы
    
    Args:
        cpp_data: CPP-данные (результат работы real_data_ingestor)
        output_dir: Директория для сохранения результатов
        config: Конфигурация SVG
        
    Returns:
        Словарь с путями к созданным HTML-файлам
    """
    if not cpp_data:
        raise ValueError("CPP-данные не предоставлены")
    
    # Создаем директорию вывода
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Настраиваем SVG-конфигурацию
    svg_config = config or SVGConfig(width=800, height=600)
    
    # Этап 1: Нормализация координат (уже выполнена в real_data_ingestor)
    print("✓ Координаты уже нормализованы")
    
    # Упрощённый маршрут без недостающих модулей компоновки/валидации
    
    # Применяем правила формирования меток ЗУ по операции (если задана)
    _apply_operation_labels(cpp_data)

    # Этап 8: Генерация SVG-графики и HTML-листов
    print("🎨 Генерация SVG-графики...")
    svg_generator = SVGGraphicsGenerator(svg_config)
    
    html_files = {}
    manifest = {"SRZU": "SRZU.html", "SGP": "SGP.html", "CH": []}
    
    # Генерируем HTML для каждого раздела
    sections = ["SRZU", "SGP", "CH"]
    section_titles = {
        "SRZU": "Схема расположения земельных участков",
        "SGP": "Схема геодезических построений", 
        "CH": "Чертеж земельных участков и их частей"
    }
    
    for section in sections:
        print(f"  📄 Генерация {section_titles[section]}...")
        
        # Генерируем SVG-графику
        if section == "CH":
            # Разбиение чертежа на страницы при необходимости
            svg_pages = svg_generator.generate_drawings_paginated(cpp_data)
            # Сохраним несколько файлов CH_pN.html
            for i, svg_content in enumerate(svg_pages, start=1):
                # Используем динамическую легенду из used_legend_tokens
                from ..graphics.labels import LegendBuilder
                if hasattr(svg_generator, 'used_legend_tokens') and svg_generator.used_legend_tokens:
                    legend_items = LegendBuilder.build(svg_generator.used_legend_tokens)
                else:
                    legend_items = generate_legend_for_data(cpp_data)
                
                scale = cpp_data.get('scales_allowed', [500])[0]
                scale_text = f"Масштаб 1:{scale}"
                html_file = output_dir / f"CH_p{i}.html"
                generate_html_sheet(
                    drawing_svg=svg_content,
                    legend_items=legend_items,
                    title=section_titles[section],
                    scale=scale_text,
                    output_path=html_file
                )
                html_files[f"CH_p{i}"] = html_file
                manifest["CH"].append(html_file.name)
            continue
        else:
            generator_section = {
                "SRZU": "SCHEME",
                "SGP": "SGP",
            }[section]
            if section == "SRZU" and isinstance(cpp_data.get('srzu'), dict):
                svg_result = render_srzu(cpp_data['srzu'], svg_config)
                if isinstance(svg_result, tuple):
                    svg_content, used_tokens = svg_result
                    # Порядок SRZU-легенды
                    order = ["target", "adjacent", "quarters", "admin", "zone", "label-quarter", "label-parcel", "boundary-existing", "boundary-new", "boundary-uncertain"]
                    # отфильтровать по used_tokens
                    ordered_tokens = [t for t in order if t in used_tokens]
                    from ..graphics.labels import LegendBuilder
                    legend_items = LegendBuilder.build(set(ordered_tokens))
                else:
                    svg_content = svg_result
                    legend_items = generate_legend_for_data(cpp_data)
            else:
                svg_content = svg_generator.generate_complete_svg(cpp_data, generator_section)
                # Для SGP также используем фактически применённые токены легенды
                from ..graphics.labels import LegendBuilder
                if hasattr(svg_generator, 'used_legend_tokens') and svg_generator.used_legend_tokens:
                    legend_items = LegendBuilder.build(svg_generator.used_legend_tokens)
                else:
                    legend_items = generate_legend_for_data(cpp_data)
        
        # Генерируем легенду для этого раздела (нормализованно через LegendBuilder)
        # legend_items = generate_legend_for_data(cpp_data) # This line is now redundant as legend_items is set above
        
        # Определяем масштаб (берем первый доступный)
        # Для SRZU и SGP масштаб не печатаем в шапке — спецификация
        scale_text = "" if section in ("SRZU", "SGP") else f"Масштаб 1:{cpp_data.get('scales_allowed', [500])[0]}"
        
        # Генерируем HTML-лист
        # Единые имена файлов по стандарту Rule 1.2
        html_file = output_dir / f"{section}.html"
        generate_html_sheet(
            drawing_svg=svg_content,
            legend_items=legend_items,
            title=section_titles[section],
            scale=scale_text,
            output_path=html_file
        )
        
        html_files[section] = html_file
        print(f"    ✅ Сохранен: {html_file}")
        if section in ("SRZU", "SGP"):
            manifest[section] = html_file.name
    
    # Пишем манифест рядом с выходными файлами
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)
    
    # Копируем CSS файл для корректного отображения схем
    _copy_css_files(output_dir)
    
    return html_files


def _copy_css_files(output_dir: Path):
    """Копирует CSS файлы в папку out для корректного отображения схем."""
    try:
        # Создаем папку css в out
        css_dir = output_dir / "css"
        css_dir.mkdir(exist_ok=True)
        
        # Путь к исходному CSS файлу
        source_css = Path(__file__).resolve().parents[3] / "public" / "css" / "sheets.css"
        
        if source_css.exists():
            # Копируем CSS файл
            shutil.copy2(source_css, css_dir / "sheets.css")
            print(f"📁 CSS файл скопирован: {css_dir / 'sheets.css'}")
        else:
            print(f"⚠️ CSS файл не найден: {source_css}")
            
    except Exception as e:
        print(f"⚠️ Ошибка копирования CSS: {e}")


def _apply_operation_labels(cpp_data: Dict[str, Any]) -> None:
    """
    Автоматически проставляет метки ЗУ согласно контексту операции (§78–79).
    
    Логика определения статуса и обозначения участка:
    
    I. Определение статуса ЗУ:
       - Если одна XML выписка → ЗУ учтенный (Уточнение/Раздел)
       - Если две и более XML выписок → ЗУ учтенные (Объединение/Перераспределение)
       - Если нет XML выписок → ЗУ вновь образуемый
    
    II. Правила обозначений:
       1. Уточнение границ (один учтенный ЗУ) → :28 (последний блок КН)
       2. Раздел/Выдел (из одного ЗУ) → :123:ЗУ1, :123:ЗУ2
       3. Объединение/Перераспределение (два и более ЗУ) → :ЗУ1, :ЗУ2 (без квартала)
       4. Части ЗУ → :123/5, :123/чзу1, :123:ЗУ1/чзу1, :ЗУ1/чзу1
    """
    entities = cpp_data.get('entities', {})
    parcels = entities.get('parcels', []) or []
    if not parcels:
        return
    
    # Проверяем количество XML выписок на исходные участки
    has_parcel_xml = cpp_data.get('has_parcel_xml', False)
    parcel_xml_count = cpp_data.get('parcel_xml_count', 0)
    
    # Функция для извлечения последнего блока кадастрового номера
    def last_block_from_cadastral(p: Dict[str, Any]) -> str:
        """Извлекает последний блок КН (например, из 04:11:010120:28 → 28)"""
        cad = p.get('cadastral_number') or ''
        if cad and ':' in cad:
            return cad.split(':')[-1]
        return cad

    op = cpp_data.get('operation') or 'CLARIFY'
    op = str(op).upper()
    counter_new = 0
    counter_parts = 0
    
    for p in parcels:
        # Если уже есть валидная метка designation — не перезаписываем
        label = p.get('designation') or ''
        if label and any(validate_label(label, kind) for kind in (
            'clarify','split','merge','part_existing','part_new_changed','part_new_split','part_new_merge'
        )):
            continue
        
        # Если designation пустое - всегда применяем правила
        
        # Определяем обозначение по типу операции
        if op == 'CLARIFY':
            # Для уточнения: если есть XML - учтенный ЗУ (:28), иначе - вновь образуемый (:ЗУ1)
            if has_parcel_xml:
                last_block = last_block_from_cadastral(p) or 'ЗУ'
                p['designation'] = ParcelLabelFormatter.base_label_for_clarify(last_block)
            else:
                counter_new += 1
                p['designation'] = ParcelLabelFormatter.new_label_for_merge(counter_new)
            
        elif op in ('SPLIT', 'ALLOT'):
            # Раздел/Выдел (из одного ЗУ) → :123:ЗУ1, :123:ЗУ2
            # Требует одну XML выписку
            if parcel_xml_count == 1:
                counter_new += 1
                quartal = last_block_from_cadastral(p) or '0'
                p['designation'] = ParcelLabelFormatter.new_label_for_split(quartal, counter_new)
            else:
                # Если нет XML - вновь образуемый
                counter_new += 1
                p['designation'] = ParcelLabelFormatter.new_label_for_merge(counter_new)
            
        elif op in ('MERGE', 'REDISTRIBUTE'):
            # Объединение/Перераспределение (два и более ЗУ) → :ЗУ1, :ЗУ2
            # Требует две и более XML выписок (или ноль - тоже вновь образуемый)
            counter_new += 1
            p['designation'] = ParcelLabelFormatter.new_label_for_merge(counter_new)
            
        elif op == 'PARTS':
            # Части ЗУ → :123/чзу1
            counter_parts += 1
            quartal = last_block_from_cadastral(p) or '0'
            p['designation'] = ParcelLabelFormatter.part_new_on_changed(quartal, counter_parts)
            
        else:
            # По умолчанию для вновь образуемого → :ЗУ1
            if has_parcel_xml:
                last_block = last_block_from_cadastral(p) or 'ЗУ'
                p['designation'] = ParcelLabelFormatter.base_label_for_clarify(last_block)
            else:
                counter_new += 1
                p['designation'] = ParcelLabelFormatter.new_label_for_merge(counter_new)


def create_project_summary_html(cpp_data: Dict[str, Any], 
                              html_files: Dict[str, Path],
                              output_dir: Path) -> Path:
    """Создает сводный HTML-файл с информацией о проекте"""
    
    project_info = cpp_data.get('project', {})
    entities = cpp_data.get('entities', {})
    
    # Собираем статистику
    stats = {
        'parcels': len(entities.get('parcels', [])),
        'boundary_points': len(entities.get('boundary_points', [])),
        'stations': len(entities.get('stations', [])),
        'directions': len(entities.get('directions', []))
    }
    
    # Читаем содержимое всех файлов для встраивания
    srzu_content = ""
    sgp_content = ""
    ch_content = ""
    
    # Читаем SRZU
    if html_files.get('SRZU'):
        try:
            with open(html_files['SRZU'], 'r', encoding='utf-8') as f:
                srzu_html = f.read()
                srzu_start = srzu_html.find('<section class="sheet"')
                srzu_end = srzu_html.find('</section>') + len('</section>')
                if srzu_start != -1 and srzu_end != -1:
                    srzu_content = srzu_html[srzu_start:srzu_end]
        except Exception as e:
            print(f"⚠️ Ошибка чтения SRZU файла: {e}")
    
    # Читаем SGP
    if html_files.get('SGP'):
        try:
            with open(html_files['SGP'], 'r', encoding='utf-8') as f:
                sgp_html = f.read()
                sgp_start = sgp_html.find('<section class="sheet"')
                sgp_end = sgp_html.find('</section>') + len('</section>')
                if sgp_start != -1 and sgp_end != -1:
                    sgp_content = sgp_html[sgp_start:sgp_end]
        except Exception as e:
            print(f"⚠️ Ошибка чтения SGP файла: {e}")
    
    # Читаем CH (первую страницу)
    ch_pages = [k for k in html_files.keys() if k.startswith('CH_p')]
    if ch_pages:
        try:
            first_ch = sorted(ch_pages)[0]
            with open(html_files[first_ch], 'r', encoding='utf-8') as f:
                ch_html = f.read()
                ch_start = ch_html.find('<section class="sheet"')
                ch_end = ch_html.find('</section>') + len('</section>')
                if ch_start != -1 and ch_end != -1:
                    ch_content = ch_html[ch_start:ch_end]
        except Exception as e:
            print(f"⚠️ Ошибка чтения CH файла: {e}")
    
    # Создаем HTML-сводку с интерфейсом табов
    html_content = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Межевой план - Сводка проекта</title>
    <link rel="stylesheet" href="css/sheets.css" />
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: #f4f4f4; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #e8f4fd; padding: 15px; border-radius: 5px; text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #0077cc; }}
        .stat-label {{ color: #666; }}
        
        /* Стили для табов */
        .tabs-container {{ margin: 30px 0; }}
        .tabs-nav {{ display: flex; border-bottom: 2px solid #ddd; margin-bottom: 20px; }}
        .tab-button {{ 
            background: #f8f9fa; 
            border: none; 
            padding: 12px 24px; 
            cursor: pointer; 
            font-size: 16px; 
            border-radius: 8px 8px 0 0; 
            margin-right: 4px;
            transition: all 0.3s ease;
        }}
        .tab-button:hover {{ background: #e9ecef; }}
        .tab-button.active {{ 
            background: #0077cc; 
            color: white; 
            font-weight: bold;
        }}
        .tab-content {{ 
            display: none; 
            padding: 20px; 
            border: 1px solid #ddd; 
            border-radius: 0 8px 8px 8px; 
            background: white;
            min-height: 600px;
        }}
        .tab-content.active {{ display: block; }}
        
        /* Стили для встроенного содержимого */
        .embedded-scheme {{ 
            margin: 15px 0; 
            border: 1px solid #ccc; 
            border-radius: 5px; 
            overflow: hidden; 
            background: white;
        }}
        .embedded-scheme .sheet {{ margin: 0; }}
        
        /* Стили для ссылок на страницы */
        .ch-pages {{ margin: 20px 0; }}
        .ch-page {{ 
            margin: 10px 0; 
            padding: 10px; 
            border: 1px solid #eee; 
            border-radius: 3px; 
            background: #f8f9fa;
        }}
        .ch-page a {{ 
            color: #0077cc; 
            text-decoration: none; 
            font-weight: bold; 
        }}
        .ch-page a:hover {{ text-decoration: underline; }}
        
        /* Стили для технической информации */
        .tech-info {{ 
            background: #f8f9fa; 
            padding: 20px; 
            border-radius: 5px; 
            margin-top: 30px; 
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Межевой план - Сводка проекта</h1>
        <h2>{project_info.get('name', 'Не указано название проекта')}</h2>
        <p><strong>ID проекта:</strong> {project_info.get('id', 'Не указан')}</p>
        <p><strong>Дата обработки:</strong> {Path().cwd().stat().st_mtime if Path().exists() else 'Неизвестно'}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-number">{stats['parcels']}</div>
            <div class="stat-label">Участков</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats['boundary_points']}</div>
            <div class="stat-label">Характерных точек</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats['stations']}</div>
            <div class="stat-label">Пунктов ОМС</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats['directions']}</div>
            <div class="stat-label">Направлений</div>
        </div>
    </div>
    
    <!-- Интерфейс с табами для схем -->
    <div class="tabs-container">
        <div class="tabs-nav">
            <button class="tab-button active" onclick="showTab('srzu')">📋 SRZU</button>
            <button class="tab-button" onclick="showTab('sgp')">📐 SGP</button>
            <button class="tab-button" onclick="showTab('ch')">🎨 CH</button>
        </div>
        
        <!-- Таб SRZU -->
        <div id="srzu" class="tab-content active">
            <h3>Схема расположения земельных участков (SRZU)</h3>
            <p>Показывает целевой ЗУ в контексте смежников и квартала с буферной зоной 200м.</p>
            <div class="embedded-scheme">
                {srzu_content if srzu_content else '<p>Схема расположения не сгенерирована</p>'}
            </div>
        </div>
        
        <!-- Таб SGP -->
        <div id="sgp" class="tab-content">
            <h3>Схема геодезических построений (SGP)</h3>
            <p>Отображает контур объекта КР, пункты ГГС/СПО, точки СГО, направления согласно правилам оформления.</p>
            <div class="embedded-scheme">
                {sgp_content if sgp_content else '<p>Схема геодезических построений не сгенерирована</p>'}
            </div>
        </div>
        
        <!-- Таб CH -->
        <div id="ch" class="tab-content">
            <h3>Чертеж земельных участков и их частей (CH)</h3>
            <p>Детальный чертеж с характерными точками, границами и подписями согласно пп. 78-79 правил оформления.</p>
            <div class="embedded-scheme">
                {ch_content if ch_content else '<p>Чертеж не сгенерирован</p>'}
            </div>
            
            <!-- Ссылки на все страницы чертежа -->
            <div class="ch-pages">
                <h4>Все страницы чертежа:</h4>
                {''.join([f'<div class="ch-page"><a href="{html_files[ch_page].name}" target="_blank">Страница {ch_page.replace("CH_p", "")}</a></div>' for ch_page in sorted(ch_pages)])}
            </div>
        </div>
    </div>
    
    <!-- Техническая информация -->
    <div class="tech-info">
        <h3>Техническая информация</h3>
        <p><strong>Система координат:</strong> {cpp_data.get('crs', {}).get('name', 'Не указана')}</p>
        <p><strong>Единицы измерения:</strong> {cpp_data.get('crs', {}).get('unit', 'Не указаны')}</p>
        <p><strong>Допустимые масштабы:</strong> 1:{', 1:'.join(map(str, cpp_data.get('scales_allowed', [])))}</p>
    </div>
    
    <script>
        function showTab(tabName) {{
            // Скрываем все табы
            const tabs = document.querySelectorAll('.tab-content');
            tabs.forEach(tab => tab.classList.remove('active'));
            
            // Убираем активный класс с всех кнопок
            const buttons = document.querySelectorAll('.tab-button');
            buttons.forEach(button => button.classList.remove('active'));
            
            // Показываем выбранный таб
            document.getElementById(tabName).classList.add('active');
            
            // Активируем соответствующую кнопку
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    
    summary_file = output_dir / "project_summary.html"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return summary_file


def run_full_pipeline_on_real_data(test_data_dir: Path, 
                                 output_dir: Path = None) -> Dict[str, Path]:
    """
    Запускает полный пайплайн на реальных данных
    
    Args:
        test_data_dir: Директория с тестовыми данными
        output_dir: Директория для результатов (по умолчанию: test_data_dir.parent / "html_results")
        
    Returns:
        Словарь с путями к созданным файлам
    """
    if output_dir is None:
        output_dir = test_data_dir.parent / "html_results"
    
    print("🚀 Запуск полного пайплайна обработки реальных данных")
    print(f"📁 Входные данные: {test_data_dir}")
    print(f"📁 Выходные данные: {output_dir}")
    
    try:
        # Этап 1: Загрузка cpp_data из JSON-контракта
        print("\n📊 Этап 1: Загрузка cpp_data из JSON...")
        data_file = test_data_dir / "real_data_cpp.json"
        cpp_data = load_cpp_data(data_file)
        
        if not cpp_data:
            raise ValueError("Не удалось обработать реальные данные")
        
        print(f"✓ Обработано {len(cpp_data.get('entities', {}).get('parcels', []))} участков")
        print(f"✓ Обработано {len(cpp_data.get('entities', {}).get('boundary_points', []))} характерных точек")
        print(f"✓ Обработано {len(cpp_data.get('entities', {}).get('stations', []))} пунктов ОМС")
        
        # Этап 2: Полный пайплайн обработки в HTML
        print("\n🎨 Этап 2: Генерация HTML-листов...")
        html_files = process_real_data_to_html(cpp_data, output_dir)
        
        # Этап 3: Создание сводки проекта
        print("\n📋 Этап 3: Создание сводки проекта...")
        summary_file = create_project_summary_html(cpp_data, html_files, output_dir)
        
        # Сохраняем CPP-данные для отладки
        cpp_file = output_dir / "processed_cpp_data.json"
        with open(cpp_file, 'w', encoding='utf-8') as f:
            json.dump(cpp_data, f, ensure_ascii=False, indent=2)
        
        result_files = {
            'summary': summary_file,
            'cpp_data': cpp_file,
            **html_files
        }
        
        print(f"\n🎉 Пайплайн завершен успешно!")
        print(f"📁 Результаты сохранены в: {output_dir}")
        print(f"📄 Сводка проекта: {summary_file}")
        
        for section, html_file in html_files.items():
            print(f"📄 {section}: {html_file}")
        
        return result_files
        
    except Exception as e:
        print(f"❌ Ошибка в пайплайне: {e}")
        raise


if __name__ == "__main__":
    # Запускаем полный пайплайн на реальных данных
    test_data_dir = Path(__file__).parent.parent.parent.parent.parent / "docs" / "МП" / "test"
    
    if test_data_dir.exists():
        try:
            result_files = run_full_pipeline_on_real_data(test_data_dir)
            print("\n✅ Все файлы успешно созданы:")
            for name, path in result_files.items():
                print(f"  {name}: {path}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"❌ Директория с тестовыми данными не найдена: {test_data_dir}")
