"""Diagnostics support for Visonic ALarm"""
from __future__ import annotations
import inspect
import json

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN, DATA

ANON_KEYS = [
    "serial",
]


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return _async_get_diagnostics(hass, entry)


@callback
def _async_get_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: DeviceEntry | None = None,
) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id][DATA]

    diag_data = {}

    # Panel Info
    diag_data.update({"RAW PANEL INFO": to_json(data.panel_info._data)})
    diag_data.update({"PANEL INFO": to_json(data.panel_info)})

    # Status
    diag_data.update({"RAW STATUS": to_json(data.status._data)})
    diag_data.update({"STATUS": to_json(data.status)})

    # Device info
    device_info = {}
    for visonic_device in data.devices:
        device_info.update({visonic_device.id: to_json(visonic_device._data)})
    diag_data.update({"RAW DEVICES": device_info})

    device_info = {}
    for visonic_device in data.devices:
        device_info.update({visonic_device.id: to_json(visonic_device)})
    diag_data.update({"DEVICES": device_info})

    return diag_data


def to_json(obj):
    """Convert object to json."""
    result = json.dumps(obj, cls=ObjectEncoder, sort_keys=True, indent=2)
    result = json.loads(result)

    if result.get("_data"):
        result.pop("_data")

    result = anonymise_data(result)
    return result


def anonymise_data(data):
    """Anonymise sensitive data."""
    for key in ANON_KEYS:
        entry = data.get(key)
        if entry:
            data[key] = "**REDACTED**"
    return data


class ObjectEncoder(json.JSONEncoder):
    """Class to encode object to json."""

    def default(self, o):
        if hasattr(o, "to_json"):
            return self.default(o.to_json())

        if hasattr(o, "__dict__"):
            data = dict(
                (key, value)
                for key, value in inspect.getmembers(o)
                if not key.startswith("__")
                and not inspect.isabstract(value)
                and not inspect.isbuiltin(value)
                and not inspect.isfunction(value)
                and not inspect.isgenerator(value)
                and not inspect.isgeneratorfunction(value)
                and not inspect.ismethod(value)
                and not inspect.ismethoddescriptor(value)
                and not inspect.isroutine(value)
            )
            return self.default(data)
        return o
