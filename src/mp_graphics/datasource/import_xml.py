from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
from xml.etree import ElementTree as ET


def parse_xml(path: str | Path) -> Dict[str, Any]:
    """Парсит упрощённый XML в ContractData (демо-импорт для тестов).

    Ожидаем структуру:
    <root>
      <project id="..." name="..."/>
      <points>
        <pt id="bp1" x="..." y="..." kind="CREATED"/>
        ...
      </points>
    </root>
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"XML не найден: {p}")

    tree = ET.parse(str(p))
    root = tree.getroot()

    project = root.find('project')
    project_info = {
        'id': (project.get('id') if project is not None else 'XML-DEMO'),
        'name': (project.get('name') if project is not None else p.stem)
    }

    pts: List[Dict[str, Any]] = []
    for el in root.findall('./points/pt'):
        try:
            x = float(el.get('x'))
            y = float(el.get('y'))
        except Exception:
            continue
        pts.append({
            'id': el.get('id') or f"bp{len(pts)+1}",
            'x': x,
            'y': y,
            'kind': el.get('kind') or 'CREATED',
        })

    data: Dict[str, Any] = {
        'project': project_info,
        'crs': {'name': 'LOCAL', 'unit': 'm'},
        'scales_allowed': [500],
        'entities': {
            'parcels': [{
                'id': 'p1', 'status': 'NEW', 'is_main': True, 'cadastral_number': ''
            }],
            'boundary_points': pts,
            'stations': [],
            'directions': [],
        }
    }
    return data


