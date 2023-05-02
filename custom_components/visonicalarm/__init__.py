"""
Support for Visonic Alarm components.

"""
import asyncio
import logging
import threading
from datetime import timedelta
from datetime import datetime

import voluptuous as vol

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import discovery
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv

from .coordinator import VisonicAlarmCoordinator
from .const import DATA, DOMAIN, UPDATE_LISTENER, VISONIC_PLATFORMS

_LOGGER = logging.getLogger(__name__)

CONF_NO_PIN_REQUIRED = "no_pin_required"
CONF_USER_CODE = "user_code"
CONF_APP_ID = "app_id"
CONF_USER_EMAIL = "user_email"
CONF_USER_PASSWORD = "user_password"
CONF_PANEL_ID = "panel_id"
CONF_PARTITION = "partition"
CONF_EVENT_HOUR_OFFSET = "event_hour_offset"

STATE_ATTR_SYSTEM_NAME = "system_name"
STATE_ATTR_SYSTEM_SERIAL_NUMBER = "serial_number"
STATE_ATTR_SYSTEM_MODEL = "model"
STATE_ATTR_SYSTEM_READY = "ready"
STATE_ATTR_SYSTEM_ACTIVE = "active"
STATE_ATTR_SYSTEM_CONNECTED = "connected"

DEFAULT_NAME = "Visonic Alarm"
DEFAULT_PARTITION = "ALL"


HUB = None

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_APP_ID): cv.string,
                vol.Required(CONF_USER_CODE): cv.string,
                vol.Required(CONF_USER_EMAIL): cv.string,
                vol.Required(CONF_USER_PASSWORD): cv.string,
                vol.Required(CONF_PANEL_ID): cv.string,
                vol.Optional(CONF_PARTITION, default=DEFAULT_PARTITION): cv.string,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_NO_PIN_REQUIRED, default=False): cv.boolean,
                vol.Optional(CONF_EVENT_HOUR_OFFSET, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=-24, max=24)
                ),
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

"""
def setup(hass, config):
    "" Setup the Visonic Alarm component.""
    from visonic import alarm as visonicalarm
    global HUB
    HUB = VisonicAlarmHub(config[DOMAIN], visonicalarm)
    if not HUB.connect():
        return False

    HUB.update()

    # Load the supported platforms
    for component in ('sensor', 'alarm_control_panel'):
        discovery.load_platform(hass, component, DOMAIN, {}, config)

    return True
"""


async def async_setup_entry(hass, config_entry):
    """Set up Wiser from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = VisonicAlarmCoordinator(hass, config_entry)

    await coordinator.async_config_entry_first_refresh()

    if not await coordinator.validate_logged_in():
        raise ConfigEntryNotReady

    # Update listener for config option changes
    update_listener = config_entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        DATA: coordinator,
        UPDATE_LISTENER: update_listener,
    }

    hass.data[DOMAIN][config_entry.entry_id] = {
        DATA: coordinator,
    }

    # Setup platforms
    for platform in VISONIC_PLATFORMS:
        hass.async_add_job(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    # Setup services
    # await async_setup_services(hass, coordinator)

    # Add hub as device
    await async_update_device_registry(hass, config_entry)

    _LOGGER.info(f"Visonic Alarm Setup Completed")
    return True


async def async_update_device_registry(hass, config_entry):
    """Update device registry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(CONNECTION_NETWORK_MAC, config_entry.data[CONF_PANEL_ID])},
        identifiers={(DOMAIN, config_entry.data[CONF_PANEL_ID])},
        manufacturer="Visonic",
        name=f"Alarm Panel",
        model=coordinator.panel_info.model,
    )


async def _async_update_listener(hass, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(hass, config_entry, device_entry) -> bool:
    """Delete device if no entities"""
    if device_entry.model == "Controller":
        _LOGGER.error(
            "You cannot delete the Wiser Controller device via the device delete method.  Please remove the integration instead."
        )
        return False
    return True


async def async_unload_entry(hass, config_entry):
    """Unload a config entry"""

    # Deregister services if only instance
    """
    _LOGGER.debug("Unregister Wiser services")
    for k, service in WISER_SERVICES.items():
        hass.services.async_remove(DOMAIN, service)
    """
    _LOGGER.debug("Unload Wiser integration platforms")
    # Unload a config entry
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, platform)
                for platform in VISONIC_PLATFORMS
            ]
        )
    )

    _LOGGER.debug("Unload integration")
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
