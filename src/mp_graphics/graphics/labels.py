"""
Логика формирования подписей и легенды для SVG/HTML.

Правила:
- Rule 2.1/2.2: Формирование подписей ЗУ и применение стилевых признаков
- Rule 2.5: Состав легенды по реально используемым типам элементов

Здесь определены утилиты, независимые от конкретного рендера SVG.
"""

import re
from typing import Dict, Any, List

from ..core.enums import ParcelStatus, PointStatus, OperationType


class ParcelLabelFormatter:
    """Формирует подписи для земельных участков по правилам 2.1/2.2.

    Возвращает только текст метки. Вопросы стилизации (курсив/подчёркивание)
    оставлены на уровень рендера и могут быть добавлены позже через атрибуты
    SVG/HTML, если потребуется внедрить Rule 2.2 в отрисовку.
    """

    @staticmethod
    def build_parcel_label(parcel: Dict[str, Any]) -> str:
        """Строит текст подписи участка.

        Предпочтение:
        - если есть `cadastral_number` с двоеточиями, берём последний блок и формируем ":NN"
        - иначе пробуем `designation` (если уже содержит ведущий двоеточие, оставляем его)
        - иначе возвращаем ":ЗУ"
        """
        cadnum = (parcel or {}).get("cadastral_number", "")
        designation = (parcel or {}).get("designation", "").strip()
        if cadnum:
            last = cadnum.split(":")[-1] if ":" in cadnum else cadnum
            last = (last or "").strip()
            return f":{last}" if last else ":ЗУ"
        if designation:
            return designation if designation.startswith(":") else f":{designation}"
        return ":ЗУ"

    # --- Формирование меток по §78–79 ---
    @staticmethod
    def base_label_for_clarify(quartal_no: str) -> str:
        return f":{quartal_no}"

    @staticmethod
    def new_label_for_split(quartal_no: str, n: int) -> str:
        return f":{quartal_no}:ЗУ{n}"

    @staticmethod
    def new_label_for_merge(n: int) -> str:
        return f":ЗУ{n}"

    @staticmethod
    def part_existing(quartal_no: str, part_no: int) -> str:
        return f":{quartal_no}/{part_no}"

    @staticmethod
    def part_new_on_changed(quartal_no: str, n: int) -> str:
        return f":{quartal_no}/чзу{n}"

    @staticmethod
    def part_new_on_split(quartal_no: str, zu_n: int, part_n: int) -> str:
        return f":{quartal_no}:ЗУ{zu_n}/чзу{part_n}"

    @staticmethod
    def part_new_on_merge(zu_n: int, part_n: int) -> str:
        return f":ЗУ{zu_n}/чзу{part_n}"


class LegendBuilder:
    """Строит элементы легенды в нормализованном формате для HTML.

    Возвращает список элементов вида:
      { 'css': 'legend-...', 'text': 'описание' }
    И совместимый старый формат через build_from_tokens -> [{'symbol','text'}].
    """

    @staticmethod
    def generate_legend_items(cpp_data: Dict[str, Any]) -> List[Dict[str, str]]:
        legend_items: List[Dict[str, str]] = []

        if not cpp_data or "entities" not in cpp_data:
            return legend_items

        entities = cpp_data["entities"] or {}
        parcels = entities.get("parcels", []) or []
        stations = entities.get("stations", []) or []
        boundary_points = entities.get("boundary_points", []) or []

        # Границы ЗУ
        has_new_parcels = any((p.get("status") == ParcelStatus.NEW) or (p.get("status") == "NEW") for p in parcels)
        has_existing_parcels = any((p.get("status") == ParcelStatus.EXISTING) or (p.get("status") == "EXISTING") for p in parcels)

        if has_new_parcels:
            legend_items.append({
                "symbol": "line-new",
                "text": "Вновь образованная граница"
            })
        if has_existing_parcels:
            legend_items.append({
                "symbol": "line-existing",
                "text": "Существующая граница"
            })

        # Характерные точки
        has_new_points = any((p.get("kind") == PointStatus.NEW) or (p.get("kind") == "CREATED") or (p.get("kind") == "NEW") for p in boundary_points)
        has_existing_points = any((p.get("kind") == PointStatus.EXISTING) or (p.get("kind") == "EXISTING") for p in boundary_points)

        if has_new_points:
            legend_items.append({
                "symbol": "point-new",
                "text": "Образуемая характерная точка"
            })
        if has_existing_points:
            legend_items.append({
                "symbol": "point-existing",
                "text": "Существующая характерная точка"
            })

        # Пункты ОМС/ГГС — токен ГГС
        if any((s.get("kind") == "GGS") for s in stations):
            legend_items.append({
                "symbol": "ggs",
                "text": "Пункт ГГС/СПО"
            })

        return legend_items

    @staticmethod
    def build(tokens: set[str]) -> List[Dict[str, str]]:
        """Новый формат легенды из токенов: возвращает [{css, text}]."""
        MAP = {
            "point-existing": {"css": "legend-point-existing", "text": "Существующая точка"},
            "point-new": {"css": "legend-point-new", "text": "Образуемая точка"},
            "point-removed": {"css": "legend-point-removed", "text": "Прекращающая точка"},
            "boundary-existing": {"css": "legend-boundary-existing", "text": "Существующая часть границы"},
            "boundary-new": {"css": "legend-boundary-new", "text": "Вновь образованная часть границы"},
            "boundary-uncertain": {"css": "legend-boundary-uncertain", "text": "Часть границы с неопределённостью"},
            "ggs": {"css": "legend-ggs", "text": "Пункт ГГС/СПО"},
            "geodir-create": {"css": "legend-geodir-create", "text": "Направление (создание съёмочного)"},
            "geodir-determine": {"css": "legend-geodir-determine", "text": "Направление (определение координат)"},
            # SRZU специфичные слои
            "target": {"css": "legend-target", "text": "Вновь образованная часть границы, сведения о которой достаточны для определения ее местоположения"},
            "adjacent": {"css": "legend-adjacent", "text": "Существующая часть границы, имеющиеся в ГКН сведения о которой достаточны для определения ее местоположения"},
            "quarters": {"css": "legend-quarters", "text": "Граница кадастрового квартала"},
            "admin": {"css": "legend-admin", "text": "Административные границы"},
            "zone": {"css": "legend-zone", "text": "Граница охранной зоны"},
            # Подписи
            "label-quarter": {"css": "legend-label-quarter", "text": "Номер кадастрового квартала"},
            "label-parcel": {"css": "legend-label-parcel", "text": "Номер земельного участка"},
            # Дополнительные элементы для КПТ
            "contour-part": {"css": "legend-contour-part", "text": "Часть контура, образованного проекцией существующего наземного конструктивного элемента здания, сооружения, объекта незавершенного строительства"},
        }
        return [{"css": MAP[t]["css"], "text": MAP[t]["text"]} for t in sorted(tokens) if t in MAP]

    @staticmethod
    def build_from_tokens(tokens: set[str]) -> List[Dict[str, str]]:
        """Старый формат: символ-токен. Оставлен для совместимости, но не используется."""
        mapping = LegendBuilder.build(tokens)
        return [{"symbol": it["css"].replace("legend-", ""), "text": it["text"]} for it in mapping]


REGEX_LABELS = {
    "clarify": r"^:\d+$",
    "split": r"^:\d+:ЗУ\d+$",
    "merge": r"^:ЗУ\d+$",
    "part_existing": r"^:\d+/\d+$",
    "part_new_changed": r"^:\d+/чзу\d+$",
    "part_new_split": r"^:\d+:ЗУ\d+/чзу\d+$",
    "part_new_merge": r"^:ЗУ\d+/чзу\d+$",
}


def validate_label(label: str, kind: str) -> bool:
    pattern = REGEX_LABELS.get(kind)
    if not pattern:
        return False
    return re.match(pattern, label) is not None


