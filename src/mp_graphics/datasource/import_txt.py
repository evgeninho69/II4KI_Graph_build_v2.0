from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List


def parse_txt(path: str | Path) -> Dict[str, Any]:
    """Парсит простой TXT с координатами "x;y" по строкам в ContractData.

    Формирует один основной участок NEW и список boundary_points.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"TXT не найден: {p}")

    points: List[Dict[str, Any]] = []
    with p.open('r', encoding='utf-8') as f:
        for idx, line in enumerate(f, start=1):
            s = line.strip()
            if not s or ';' not in s:
                continue
            
            # Поддерживаем форматы: "X;Y" и "номер;X;Y"
            parts = s.split(';')
            if len(parts) == 2:
                # Формат "X;Y"
                xs, ys = parts
            elif len(parts) == 3:
                # Формат "номер;X;Y"
                _, xs, ys = parts
            else:
                continue
                
            try:
                x = float(xs.replace(',', '.'))
                y = float(ys.replace(',', '.'))
            except ValueError:
                continue
            points.append({
                'id': f'bp{idx}',
                'x': x,
                'y': y,
                'kind': 'CREATED',
            })

    data: Dict[str, Any] = {
        'project': {'id': 'TXT-DEMO', 'name': p.stem},
        'crs': {'name': 'LOCAL', 'unit': 'm'},
        'scales_allowed': [500],
        'entities': {
            'parcels': [{
                'id': 'p1', 'status': 'NEW', 'is_main': True, 'cadastral_number': '',
            }],
            'boundary_points': points,
            'stations': [],
            'directions': [],
        }
    }
    return data


def parse_stations_txt(path: str | Path) -> List[Dict[str, Any]]:
    """Парсит TXT файл со списком пунктов ОМС в формате TSV."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл станций не найден: {p}")

    stations: List[Dict[str, Any]] = []
    
    with p.open('r', encoding='utf-8') as f:
        lines = f.readlines()
        
        # Пропускаем заголовок (первая строка)
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
                
            # Разделяем по табу
            parts = line.split('\t')
            if len(parts) < 8:  # Минимум 8 колонок
                continue
                
            try:
                # Извлекаем данные
                station_id = parts[0].strip()
                network_type = parts[1].strip()
                station_name = parts[2].strip()
                address = parts[3].strip()
                network_class = parts[4].strip()
                marker_type = parts[5].strip()
                x = float(parts[6].replace(',', '.'))
                y = float(parts[7].replace(',', '.'))
                
                stations.append({
                    'id': station_id,
                    'name': station_name,
                    'x': x,
                    'y': y,
                    'kind': 'OMS',
                    'network_type': network_type,
                    'network_class': network_class,
                    'marker_type': marker_type,
                    'address': address
                })
                
            except (ValueError, IndexError):
                continue
                
    return stations


