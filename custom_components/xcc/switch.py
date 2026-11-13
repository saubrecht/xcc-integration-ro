"""Compatibility placeholder for unloading the former writable platform.

Values are now exposed by sensor.py and binary_sensor.py.
"""


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Register no controls; this integration only exposes read-only entities."""
