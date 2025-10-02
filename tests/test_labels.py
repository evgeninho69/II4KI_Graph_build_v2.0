from mp_graphics.graphics.labels import ParcelLabelFormatter as F, validate_label


def test_label_patterns():
    assert F.base_label_for_clarify("123") == ":123"
    assert validate_label(":123", "clarify")

    assert F.new_label_for_split("123", 1) == ":123:ЗУ1"
    assert validate_label(":123:ЗУ1", "split")

    assert F.new_label_for_merge(1) == ":ЗУ1"
    assert validate_label(":ЗУ1", "merge")

    assert F.part_existing("123", 5) == ":123/5"
    assert validate_label(":123/5", "part_existing")

    assert F.part_new_on_changed("123", 1) == ":123/чзу1"
    assert validate_label(":123/чзу1", "part_new_changed")

    assert F.part_new_on_split("123", 1, 1) == ":123:ЗУ1/чзу1"
    assert validate_label(":123:ЗУ1/чзу1", "part_new_split")

    assert F.part_new_on_merge(1, 1) == ":ЗУ1/чзу1"
    assert validate_label(":ЗУ1/чзу1", "part_new_merge")


