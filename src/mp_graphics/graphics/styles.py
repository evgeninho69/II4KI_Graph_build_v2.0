POINT_DIAMETER_MM: float = 1.5
LINE_WIDTH_MM: float = 0.2
GEODIR_CREATE_MM: float = 0.5  # СГП: создание съёмочного обоснования
DASH_MM = (2.0, 1.0)           # пунктир 2/1 мм для UNCERTAIN

COLORS = {
    "black": "#000000",
    "red": "#ff0000",
    "gray": "#808080",
}

LEGEND_TOKENS = {
    "point-existing": "Существующая точка",
    "point-new": "Новая точка",
    "point-removed": "Прекращающая существование точка",
    "boundary-existing": "Существующая часть границы",
    "boundary-new": "Вновь образованная часть границы",
    "boundary-uncertain": "Часть границы с недостаточной определённостью",
    "ggs": "Пункт ГГС/СПО",
    "oms": "Пункт ОМС",
    "geodir-create": "Направление (создание съёмочного обоснования)",
    "geodir-determine": "Направление (определение координат)",
}


