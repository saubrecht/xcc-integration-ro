"""Regression checks for the XCC parent/sub-device relationship."""

from pathlib import Path


REPO = Path(__file__).parent.parent
XCC = REPO / "custom_components" / "xcc"


def test_sub_devices_use_the_parent_device_id_not_deprecated_identifier_link():
    """The device registry must receive the supported parent ID field."""
    coordinator = (XCC / "coordinator.py").read_text(encoding="utf-8")
    entity = (XCC / "entity.py").read_text(encoding="utf-8")
    setup = (XCC / "__init__.py").read_text(encoding="utf-8")

    assert '"via_device_id": self.parent_device_id' in coordinator
    assert "via_device_id=device_info.get(\"via_device_id\")" in entity
    assert "via_device=" not in entity
    assert "coordinator.parent_device_id = main_device.id" in setup
