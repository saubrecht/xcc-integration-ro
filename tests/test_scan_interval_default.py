"""Regression checks for scan-interval configuration."""

import importlib.util
from pathlib import Path


REPO = Path(__file__).parent.parent
COORDINATOR = REPO / "custom_components" / "xcc" / "coordinator.py"
XCC_CLIENT = REPO / "custom_components" / "xcc" / "xcc_client.py"


def test_default_scan_interval():
    """The default polling period is 12 minutes."""
    spec = importlib.util.spec_from_file_location(
        "xcc_const", REPO / "custom_components" / "xcc" / "const.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.DEFAULT_SCAN_INTERVAL == 720


def test_xcc_request_delay_is_1_point_2_seconds():
    """Page polling is paced to protect the controller's single connection."""
    spec = importlib.util.spec_from_file_location(
        "xcc_const", REPO / "custom_components" / "xcc" / "const.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.REQUEST_DELAY_SECONDS == 1.2


def test_authentication_retry_backoff_starts_at_four_seconds():
    """Failed authentication retries wait four seconds, then eight seconds."""
    source = XCC_CLIENT.read_text(encoding="utf-8")
    authenticate = source.split("async def _authenticate", 1)[1].split(
        "def _save_session", 1
    )[0]

    assert "retry_delay = 4" in authenticate
    assert "retry_delay *= 2" in authenticate


def test_options_scan_interval_overrides_initial_config_value():
    """A Configure-flow interval takes effect after its entry reloads.

    This intentionally verifies the coordinator's initialization path without
    importing Home Assistant's coordinator base class in this lightweight test
    suite.
    """
    source = COORDINATOR.read_text(encoding="utf-8")
    options_lookup = source.index("entry.options.get(", source.index("scan_interval"))
    data_lookup = source.index("entry.data.get(CONF_SCAN_INTERVAL", options_lookup)

    assert options_lookup < data_lookup
