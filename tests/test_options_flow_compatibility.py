"""Regression checks for current Home Assistant options-flow support."""

from pathlib import Path


CONFIG_FLOW = (
    Path(__file__).parent.parent / "custom_components" / "xcc" / "config_flow.py"
)


def test_options_flow_does_not_assign_read_only_config_entry_property():
    """Opening Configure must work on Home Assistant versions with OptionsFlow properties."""
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    options_flow = source.split("class XCCOptionsFlowHandler", 1)[1]

    assert "return XCCOptionsFlowHandler()" in source
    assert "def __init__" not in options_flow
    assert "self.config_entry =" not in options_flow
