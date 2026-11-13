"""Read-only entities retain numeric and boolean controller setting values."""

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.xcc.entity import XCCEntity


@pytest.mark.parametrize("data_type,value,expected", [
    ("bool", "0", False),
    ("bool", "1", True),
    ("boolean", "false", False),
    ("real", "22.5", 22.5),
    ("numeric", "21.0", 21.0),
    ("int", "2", 2),
])
def test_setting_value_conversion(data_type, value, expected):
    entity = SimpleNamespace(_attributes={"data_type": data_type})
    result = XCCEntity._convert_value_for_ha(entity, value)
    assert result == expected
    assert type(result) is type(expected)


def test_controller_writable_metadata_does_not_advertise_ha_writes():
    entity = SimpleNamespace(
        entity_id_suffix="xcc_okruh1_povoleni",
        _entity_data={"prop": "OKRUH1-POVOLENI", "page": "OKRUH11.XML",
                      "descriptor_config": {"writable": True}},
        _attributes={"data_type": "bool", "is_settable": True},
    )
    attrs = XCCEntity.extra_state_attributes.fget(entity)
    assert attrs["xcc_settable"] is False
