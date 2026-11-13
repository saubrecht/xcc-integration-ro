"""Regression checks for the integration's read-only boundary."""

from pathlib import Path


REPO = Path(__file__).parent.parent


def test_only_sensor_platform_is_forwarded():
    """Reloading the entry must not restore a writable entity platform."""
    source = (REPO / "custom_components" / "xcc" / "__init__.py").read_text(
        encoding="utf-8"
    )
    platforms = source.split("PLATFORMS_TO_SETUP = [", 1)[1].split("]", 1)[0]

    assert "Platform.SENSOR" in platforms
    assert "Platform.BINARY_SENSOR" in platforms
    for platform in ("SWITCH", "NUMBER", "SELECT", "BUTTON"):
        assert f"Platform.{platform}" not in platforms


def test_integration_has_no_write_entry_points():
    """Neither controls, entities, coordinator nor client can write values."""
    import ast

    forbidden = {
        "set_value", "async_set_value", "async_set_entity_value",
        "async_set_xcc_value", "async_set_native_value", "async_select_option",
        "async_turn_on", "async_turn_off", "async_press",
    }
    for path in (REPO / "custom_components" / "xcc").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        methods = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not methods & forbidden, path.name


def test_coordinator_holds_its_lock_for_the_complete_poll():
    """The shared HTTP client must not be used by concurrent poll tasks."""
    source = (REPO / "custom_components" / "xcc" / "coordinator.py").read_text(
        encoding="utf-8"
    )
    wrapper = source.split("async def _async_update_data(", 1)[1].split(
        "async def _async_update_data_locked", 1
    )[0]

    assert "async with self._update_lock:" in wrapper
    assert "return await self._async_update_data_locked()" in wrapper


def test_hidden_switch_analysis_is_not_consumed_by_the_integration():
    """Offline switch analysis must not introduce writable HA control overrides."""
    const_source = (REPO / "custom_components" / "xcc" / "const.py").read_text(
        encoding="utf-8"
    )

    assert "HIDDEN_SWITCHES:" not in const_source
    assert "TO-CONFIG-CHLAZENI" not in const_source
