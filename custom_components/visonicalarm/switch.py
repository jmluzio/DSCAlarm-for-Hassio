import asyncio
import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity
from .const import (
    CONF_PANEL_ID,
    DOMAIN,
    DATA,
    SENSOR_TYPE_FRIENDLY_NAME,
    SUPPORTED_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Visonic Alarm platform switches"""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    switches = []

    for device in coordinator.devices:
        if device and device.subtype and device.subtype in SUPPORTED_SENSORS:
            if hasattr(device, "bypass") and getattr(device, "bypass") != None:
                _LOGGER.debug("Adding panel status sensor")
                switches.append(VisonicAlarmSwitch(coordinator, device, "bypass"))
                continue

    async_add_entities(switches)


class VisonicAlarmSwitch(CoordinatorEntity, SwitchEntity):
    """Implementation of a Visonic Alarm Contact sensor."""

    def __init__(self, coordinator, device, switch_type=None, status=None):
        """Initialise switch"""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._alarm = self.coordinator.alarm
        self._device = device
        self._switch_type = switch_type

    def get_base_name(self):
        if self._device.subtype in SENSOR_TYPE_FRIENDLY_NAME:
            name = f"{SENSOR_TYPE_FRIENDLY_NAME[self._device.subtype]}"
        else:
            name = f"{self._device.subtype}"

        if hasattr(self._device, "location") and self._device.location:
            name = f"{self._device.location} {name}"

        if SENSOR_TYPE_FRIENDLY_NAME[self._device.subtype] == "Keyfob":
            if hasattr(self._device, "owner_name"):
                name = f"{name} {self._device.owner_name}"
            else:
                name = f"{name} {self._device.device_number}"

        return name

    async def async_force_update(self, delay: int = 0):
        _LOGGER.debug(f"Alarm update initiated by {self.name}")
        if delay:
            await asyncio.sleep(delay)
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the latest data"""
        try:
            self._device = self.coordinator.get_device_by_id(self._device.id)
            self.async_write_ha_state()

        except OSError as error:
            _LOGGER.warning(f"Could not update the device information: {error}")

    @property
    def is_on(self) -> bool | None:
        return self._device.bypass

    @property
    def name(self):
        """Return the name of the sensor"""
        if self._switch_type:
            return f"{self.get_base_name()} {str(self._switch_type).capitalize()}"

        return self.get_base_name()

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-{self._device.id}{self._switch_type}"

    @property
    def device_info(self):
        return {
            "name": self.get_base_name(),
            "identifiers": {
                (DOMAIN, f"{self.coordinator.panel_info.serial}-{self._device.id}")
            },
            "manufacturer": "Visonic",
            "model": self._device.subtype
            if self._device.subtype != "VISONIC_PANEL"
            else self.coordinator.panel_info.model,
            "serial_number": self._device.id,
            "product_type": self._device.subtype,
            "product_identifier": self._device.id,
            "via_device": (DOMAIN, self.coordinator.config_entry.data[CONF_PANEL_ID]),
        }

    @property
    def icon(self):
        """Return icon"""
        return "mdi:motion-sensor-off"

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        await self.hass.async_add_executor_job(
            self._alarm.set_bypass_zone, self._device.device_number, True
        )
        await self.async_force_update()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self.hass.async_add_executor_job(
            self._alarm.set_bypass_zone, self._device.device_number, False
        )
        await self.async_force_update()
        return True
