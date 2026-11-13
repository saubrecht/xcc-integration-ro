"""Controller settings remain observable without exposing HA controls."""

import importlib.util
import sys
from pathlib import Path

import pytest

XCC = Path(__file__).resolve().parents[1] / "custom_components" / "xcc"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, XCC / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


helpers = load("_readonly_helpers", "entity_helpers.py")
parser = load("descriptor_parser", "descriptor_parser.py")
client = load("_readonly_client", "xcc_client.py")


@pytest.mark.parametrize(
    "source_type,expected_type,bucket,value",
    [
        ("number", "sensor", "sensors", "22.5"),
        ("select", "sensor", "sensors", "2"),
        ("switch", "binary_sensor", "binary_sensors", "1"),
        ("button", "sensor", "sensors", "0"),
    ],
)
@pytest.mark.parametrize("described", [True, False])
def test_settings_are_observable(source_type, expected_type, bucket, value, described):
    raw = {
        "entity_type": source_type,
        "state": value,
        "attributes": {"field_name": "SETTING", "page": "NAST2.XML"},
    }
    configs = {"SETTING": {"entity_type": source_type, "writable": True}} if described else {}
    data, metadata = helpers.process_entities([raw], configs, "czech")
    assert data[bucket]["xcc_setting"]["state"] == value
    assert metadata["xcc_setting"]["type"] == expected_type
    assert all(not data[k] for k in ("switches", "numbers", "selects", "buttons"))
    if described:
        assert configs["SETTING"]["entity_type"] == source_type


def test_secondary_circuit_setpoint_from_real_xml():
    samples = Path(__file__).parent / "sample_data"
    descriptor = (samples / "okruh.xml").read_text(encoding="utf-8")
    configs = parser.XCCDescriptorParser(ignore_visibility=True).parse_descriptor_files(
        {"okruh.xml": descriptor}
    )
    raw = []
    for page in ("OKRUH10.XML", "OKRUH12.XML"):
        xml = (samples / page).read_bytes().decode("windows-1250")
        raw.extend(client.parse_xml_entities(xml, page))
    data, metadata = helpers.process_entities(raw, configs, "czech")
    for entity_id, value in (("xcc_to_pozadovana", "21.0"), ("xcc_okruh2_pozadovana", "22.5")):
        assert data["sensors"][entity_id]["state"] == value
        assert metadata[entity_id]["device"] == "OKRUH"
        assert metadata[entity_id]["descriptor_config"]["unit"] == "°C"
    assert "xcc_okruh2_povoleni" in data["binary_sensors"]
    assert metadata["xcc_okruh2_pozadovana"]["descriptor_config"]["friendly_name"]
    assert all(not data[k] for k in ("switches", "numbers", "selects", "buttons"))


def test_readonly_choice_preserves_options():
    configs = parser.XCCDescriptorParser(ignore_visibility=True).parse_descriptor_files({
        "nast.xml": '<page><row text="Režim"><choice config="readonly" prop="MODE">'
        '<option value="0" text="Vypnuto"/><option value="1" text="Zapnuto"/>'
        '</choice></row></page>'
    })
    assert configs["MODE"]["options"]
    raw = {"state": "1", "attributes": {"field_name": "MODE", "page": "NAST1.XML"}}
    data, metadata = helpers.process_entities([raw], configs, "czech")
    assert data["sensors"]["xcc_mode"]["state"] == "1"
    assert metadata["xcc_mode"]["descriptor_config"]["options"] == configs["MODE"]["options"]
