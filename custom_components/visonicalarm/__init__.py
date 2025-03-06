"""
Support for Visonic Alarm components.

"""
import asyncio
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from .coordinator import VisonicAlarmCoordinator
from .const import CONF_PANEL_ID, DATA, DOMAIN, UPDATE_LISTENER, VISONIC_PLATFORMS

_LOGGER = logging.getLogger(__name__)


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
    await hass.config_entries.async_forward_entry_setups(config_entry, VISONIC_PLATFORMS)

    # Setup services
    # await async_setup_services(hass, coordinator)

    # Add hub as device
    await async_update_device_registry(hass, config_entry)

    _LOGGER.info("Visonic Alarm Setup Completed")
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
        name="Alarm Panel",
        model=coordinator.panel_info.model,
    )


async def _async_update_listener(hass, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(hass, config_entry, device_entry) -> bool:
    """Delete device if no entities"""
    if device_entry.model == "Controller":
        _LOGGER.error(
            "You cannot delete the Alarm panel device via the device delete method. %s",
            "Please remove the integration instead.",
        )
        return False
    return True


async def async_unload_entry(hass, config_entry):
    """Unload a config entry"""
    _LOGGER.debug("Unload Visonic integration platforms")
    # Unload a config entry
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(config_entry, platform) for platform in VISONIC_PLATFORMS]
        )
    )

    _LOGGER.debug("Unload integration")
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
