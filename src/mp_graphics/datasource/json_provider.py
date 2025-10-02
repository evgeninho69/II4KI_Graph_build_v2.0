from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_cpp_data(json_path: Path | str) -> Dict[str, Any]:
    """Загружает cpp_data из JSON по согласованному контракту (Rule 6.1)."""
    p = Path(json_path)
    if not p.exists():
        raise FileNotFoundError(f"JSON не найден: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "entities" not in data:
        raise ValueError("Неверный формат cpp_data: ожидается объект с ключом 'entities'")
    return data


