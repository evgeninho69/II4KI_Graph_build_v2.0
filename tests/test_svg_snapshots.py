from mp_graphics.graphics.svg_generator import SVGConfig, generate_svg_for_section


def make_cpp_data(points, kind="CREATED", status="NEW"):
    return {
        "project": {"id": "T-001", "name": "Test Project"},
        "crs": {"name": "LOCAL", "unit": "m"},
        "scales_allowed": [500],
        "entities": {
            "parcels": [
                {"id": "p1", "status": status, "is_main": True, "cadastral_number": "01:02:03:123"}
            ],
            "boundary_points": [
                {"id": f"bp{i+1}", "x": x, "y": y, "kind": kind} for i, (x, y) in enumerate(points)
            ],
            "stations": [],
            "directions": [],
        },
    }


def test_drawing_new_parcel_snapshot(file_regression):
    # Квадрат 200x200 с центром в (0,0) — даёт чистые нормализованные координаты
    points = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    cpp_data = make_cpp_data(points, kind="CREATED", status="NEW")
    svg = generate_svg_for_section(cpp_data, section_type="DRAWING", config=SVGConfig(width=800, height=600))
    file_regression.check(svg, basename="drawing_new_parcel", extension=".svg")


def test_scheme_existing_parcel_snapshot(file_regression):
    points = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    cpp_data = make_cpp_data(points, kind="EXISTING", status="EXISTING")
    svg = generate_svg_for_section(cpp_data, section_type="SCHEME", config=SVGConfig(width=800, height=600))
    file_regression.check(svg, basename="scheme_existing_parcel", extension=".svg")


def test_sgp_contains_required_elements():
    cpp_data = {
        "project": {"id": "T-002", "name": "Test SGP"},
        "crs": {"name": "LOCAL", "unit": "m"},
        "scales_allowed": [500],
        "entities": {
            "parcels": [{"id": "p1", "status": "NEW", "is_main": True, "cadastral_number": "11:22:33:444"}],
            "boundary_points": [
                {"id": "bp1", "x": 0.0, "y": 0.0, "kind": "CREATED"},
                {"id": "bp2", "x": 100.0, "y": 0.0, "kind": "CREATED"},
                {"id": "bp3", "x": 100.0, "y": 100.0, "kind": "CREATED"},
                {"id": "bp4", "x": 0.0, "y": 100.0, "kind": "CREATED"},
            ],
            "stations": [
                {"id": "s1", "x": 200.0, "y": 0.0, "name": "ОМС-1", "kind": "OMS"}
            ],
            "directions": [
                {"from_station_id": "s1", "to_point_id": "bp2", "length_m_int": 100}
            ],
        },
    }
    svg = generate_svg_for_section(cpp_data, section_type="SGP", config=SVGConfig(width=800, height=600))
    # Проверяем наличие базовых элементов: линия направления 0.2мм со стрелкой, символ пункта, подпись расстояния
    assert "stroke-width=\"0.2mm\"" in svg
    assert "marker-end=\"url(#arrowhead)\"" in svg
    assert "rect" in svg or "<rect" in svg  # символ ОМС
    assert " м</text>" in svg or "м</text>" in svg


