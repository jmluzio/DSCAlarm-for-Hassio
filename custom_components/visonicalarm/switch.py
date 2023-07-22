import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA, DOMAIN, SUPPORTED_SENSORS
from .entity import BaseVisonicEntity

_LOGGER = logging.getLogger(__name__)

SWITCHES = [
    {
        "type": "device",
        "name": "bypass",
        "function": "set_bypass_zone",
        "require_device_id": True,
    },
]
"""
    {
        "type": "panel",
        "name": "siren",
        "on_function": "activate_siren",
        "off_function": "disable_siren",
        "require_device_id": False,
    },
"""


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Visonic Alarm platform switches"""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    switches = []

    # Device switches
    for device in coordinator.devices:
        if device and device.subtype and device.subtype in SUPPORTED_SENSORS:
            for switch in [switch for switch in SWITCHES if switch["type"] == "device"]:
                if hasattr(device, switch["name"]) and getattr(device, switch["name"]) is not None:
                    _LOGGER.debug("Adding %s switch for %s", switch["name"], BaseVisonicEntity.get_base_name(device))
                    switches.append(VisonicAlarmDeviceSwitch(coordinator, device, switch))
                    continue

    # Panel switches
    for switch in [switch for switch in SWITCHES if switch["type"] == "panel"]:
        _LOGGER.debug("Adding %s switch for %s", switch["name"], BaseVisonicEntity.get_base_name())
        switches.append(VisonicAlarmPanelSwitch(coordinator, switch))

    async_add_entities(switches)


class VisonicAlarmSwitch(BaseVisonicEntity, CoordinatorEntity, SwitchEntity):
    """Implementation of a Visonic Alarm Contact sensor."""

    def __init__(self, coordinator, switch_info):
        """Initialise switch"""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._alarm = self.coordinator.alarm
        self._device = None
        self._switch_info = switch_info
        self._switch_type = switch_info["name"]

    async def async_force_update(self, delay: int = 0):
        """Force update from alarm panel."""
        _LOGGER.debug("Alarm update initiated by %s", self.name)
        if delay:
            await asyncio.sleep(delay)
        await self.coordinator.async_refresh()

    @property
    def is_on(self) -> bool | None:
        """Return if is on."""
        return self._device.bypass

    @property
    def name(self):
        """Return the name of the sensor"""
        if self._switch_type:
            return f"{self.get_base_name(self._device)} {str(self._switch_type).capitalize()}"

        return self.get_base_name(self._device)

    @property
    def unique_id(self):
        """Return unique id."""
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-{self._device.id}{self._switch_type}"

    @property
    def icon(self):
        """Return icon"""
        return "mdi:motion-sensor-off"

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        return await self.async_set_switch(self._switch_info, True)

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        return await self.async_set_switch(self._switch_info, False)

    async def async_set_switch(self, switch_info: dict, state: bool) -> bool:
        """Set switch status."""
        # Establish correct function to call
        if switch_info.get("on_function") and state:
            func = getattr(self._alarm, switch_info["on_function"])
        elif switch_info.get("off_function") and not state:
            func = getattr(self._alarm, switch_info["off_function"])
        else:
            func = getattr(self._alarm, switch_info["function"])

        if switch_info.get("require_device_id"):
            token = await self.hass.async_add_executor_job(
                func,
                self._device.device_number,
                state,
            )
        else:
            token = await self.hass.async_add_executor_job(
                func,
            )

        if not await self.async_wait_for_process_success(self.coordinator, token):
            raise HomeAssistantError(f"There was an error setting the {switch_info['name']} on {self.name}")
        await self.async_force_update()
        return True


class VisonicAlarmDeviceSwitch(VisonicAlarmSwitch):
    """Class for device switch."""

    def __init__(self, coordinator, device, switch_info):
        """Initialise switch"""
        super().__init__(coordinator, switch_info)
        self._device = device
        self._is_on = getattr(self._device, self._switch_info["name"])

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the latest data"""
        try:
            self._device = self.coordinator.get_device_by_id(self._device.id)
            self._is_on = getattr(self._device, self._switch_info["name"])
            self.async_write_ha_state()

        except OSError as error:
            _LOGGER.warning("Could not update the device information: %s", error)

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-{self._device.id}{self._switch_type}"

    @property
    def icon(self):
        """Return icon"""
        return "mdi:motion-sensor-off"


class VisonicAlarmPanelSwitch(VisonicAlarmSwitch):
    """Class for panel switch."""

    def __init__(self, coordinator, switch_info):
        """Initialise switch"""
        super().__init__(coordinator, switch_info)
        self._is_on = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the latest data"""
        try:
            # self._alarm = self.coordinator.get_device_by_id(self._device.id)
            # self._is_on = getattr(self._device, self._switch_info["name"])
            self.async_write_ha_state()

        except OSError as error:
            _LOGGER.warning("Could not update the device information: %s", error)

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-{self._switch_type}"

    @property
    def icon(self):
        """Return icon"""
        return "mdi:motion-sensor-off"
