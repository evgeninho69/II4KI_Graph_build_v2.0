from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ParcelStatus(Enum):
    EXISTING = auto()
    NEW = auto()
    REMOVED = auto()


class BoundaryStatus(Enum):
    EXISTING = auto()      # сплошная чёрная 0.2 мм
    NEW = auto()           # сплошная красная 0.2 мм
    UNCERTAIN = auto()     # пунктир 2/1 мм, 0.2 мм


class PointStatus(Enum):
    EXISTING = auto()
    NEW = auto()
    REMOVED = auto()


class OperationType(Enum):
    CLARIFY = auto()
    SPLIT = auto()
    ALLOT = auto()
    MERGE = auto()
    REDISTRIBUTE = auto()
    PARTS = auto()


__all__ = ["ParcelStatus", "BoundaryStatus", "PointStatus", "OperationType"]


