"""Exercise whole polling cycles against a fake controller and HA registry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.xcc.coordinator import XCCDataUpdateCoordinator

PAGES = ["NAST1.XML", "NAST2.XML", "NAST3.XML"]
IP = "192.0.2.1"


def xml(**values):
    return '<PAGE>' + ''.join(
        f'<INPUT P="{key}" NAME="__R1_REAL_.1f" VALUE="{value}"/>'
        for key, value in values.items()
    ) + '</PAGE>'


def registry_entry(key, *, disabled=False, hidden=False, domain="sensor", platform="xcc"):
    return SimpleNamespace(
        domain=domain, platform=platform, unique_id=f"{IP}_{key}",
        disabled_by="user" if disabled else None,
        hidden_by="user" if hidden else None,
        entity_id="sensor.renamed_by_user",
    )


@pytest.fixture
def coordinator():
    c = object.__new__(XCCDataUpdateCoordinator)
    c.hass = Mock()
    c.entry = SimpleNamespace(entry_id="test-xcc")
    c.ip_address = IP
    c.language = "czech"
    c._pages_discovered = c._descriptors_loaded = True
    c._discovered_data_pages = list(PAGES)
    c._page_entities = {}
    c._page_filter_ready = False
    c.entities = {}
    c.entity_configs = {}
    c.device_info = {"name": "Test controller"}
    c._note_gather_result = Mock()
    c._client = SimpleNamespace(
        fetch_pages=AsyncMock(return_value={
            PAGES[0]: xml(SHARED="10"),
            PAGES[1]: xml(SHARED="20", SECOND="30"),
            PAGES[2]: xml(),
        }),
        fetch_page=AsyncMock(return_value="<PAGE/>"),
        parse_main_xml_config_entities=Mock(return_value=[]),
    )
    return c


@pytest.mark.asyncio
async def test_startup_filtering_and_reenable(coordinator):
    c = coordinator
    entries = [registry_entry("xcc_shared"), registry_entry("xcc_second", disabled=True)]
    with patch("custom_components.xcc.coordinator.er.async_get", return_value=Mock()), patch(
        "custom_components.xcc.coordinator.er.async_entries_for_config_entry", return_value=entries
    ) as get_entries:
        await c._async_update_data_locked()
        assert c._client.fetch_pages.call_args.args[0] == PAGES
        get_entries.assert_not_called()  # Startup always performs full discovery.
        c._client.fetch_pages.return_value = {PAGES[0]: xml(SHARED="11")}
        data = await c._async_update_data_locked()
        assert c._client.fetch_pages.call_args.args[0] == [PAGES[0]]
        assert data["sensors"]["xcc_shared"]["state"] == "11"
        assert c.entities["xcc_shared"]["page"] == PAGES[0]
        assert "xcc_second" in c.entities  # Retained for future re-enabling.
        c._note_gather_result.assert_called_with([], poll_failed=False, expected=1)

        # Re-enable while hidden: no reload or display-name matching required.
        entries[1] = registry_entry("xcc_second", hidden=True)
        c._client.fetch_pages.return_value = {PAGES[0]: xml(SHARED="12"), PAGES[1]: xml(SHARED="22", SECOND="32")}
        data = await c._async_update_data_locked()
        assert c._client.fetch_pages.call_args.args[0] == PAGES[:2]
        assert data["sensors"]["xcc_second"]["state"] == "32"
        assert data["sensors"]["xcc_shared"]["state"] == "12"
        get_entries.assert_called_with(get_entries.call_args.args[0], "test-xcc")

        entries[:] = [registry_entry("xcc_shared", disabled=True), registry_entry("xcc_second", disabled=True)]
        c._client.fetch_pages.return_value = {}
        await c._async_update_data_locked()
        assert c._client.fetch_pages.call_args.args[0] == []
        c._note_gather_result.assert_called_with([], poll_failed=False, expected=0)
        assert c._client.fetch_page.await_count == 4  # main.xml is always retained.


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, "Error: Timeout", "<PAGE>"])
async def test_missing_and_malformed_pages_are_retried(coordinator, response):
    c = coordinator
    if response is None:
        del c._client.fetch_pages.return_value[PAGES[2]]
    else:
        c._client.fetch_pages.return_value[PAGES[2]] = response
    await c._async_update_data_locked()
    assert PAGES[2] not in c._page_entities
    c._note_gather_result.assert_called_with([PAGES[2]], poll_failed=False, expected=3)
    with patch("custom_components.xcc.coordinator.er.async_get", return_value=Mock()), patch(
        "custom_components.xcc.coordinator.er.async_entries_for_config_entry", return_value=[]
    ):
        assert c._select_data_pages(PAGES) == PAGES


@pytest.mark.asyncio
async def test_now_empty_page_loses_its_metadata(coordinator):
    c = coordinator
    await c._async_update_data_locked()
    c._client.fetch_pages.return_value = {PAGES[0]: xml(), PAGES[1]: xml(SECOND="30")}
    with patch("custom_components.xcc.coordinator.er.async_get", return_value=Mock()), patch(
        "custom_components.xcc.coordinator.er.async_entries_for_config_entry", return_value=[]
    ):
        await c._async_update_data_locked()
        assert "xcc_shared" not in c.entities
        assert c._select_data_pages(PAGES) == [PAGES[1]]
