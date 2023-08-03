"""Base visonic entity"""

import asyncio
import logging
from datetime import datetime

from dateutil import tz
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyvisonicalarm.devices import Device as VisonicDevice

from .const import CONF_PANEL_ID, DOMAIN, PROCESS_TIMEOUT, SENSOR_TYPE_FRIENDLY_NAME

_LOGGER = logging.getLogger(__name__)


class BaseVisonicEntity:
    """Base for Visonic HA entity."""

    _device: VisonicDevice
    coordinator: DataUpdateCoordinator

    @staticmethod
    def get_base_name(device=None, partition_id: int = 0):
        """Get device name"""
        if not device:
            return "Alarm Panel"
        if device.subtype in SENSOR_TYPE_FRIENDLY_NAME:
            name = f"{SENSOR_TYPE_FRIENDLY_NAME[device.subtype]}"
        else:
            name = f"{device.subtype}"

        if hasattr(device, "location") and device.location:
            name = f"{device.location} {name}"

        if SENSOR_TYPE_FRIENDLY_NAME[device.subtype] in ["Keyfob", "Tag"]:
            if hasattr(device, "owner_name") and device.owner_name:
                name = f"{name} {device.owner_name}"
            elif hasattr(device, "name") and device.name:
                name = f"{name} {device.name}"
            else:
                name = f"{name} {device.device_number}"

        return name

    def convert_to_local_datetime(self, dt: datetime) -> datetime:  # pylint: disable=invalid-name
        """Convert datetime to local timezone"""
        utc = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        utc = utc.replace(tzinfo=tz.tzutc())
        return utc.astimezone(tz.tzlocal())

    async def async_wait_for_process_success(self, coordinator, process_token) -> bool:
        """Wait for process command to compelte."""
        timeout = 0
        while timeout <= PROCESS_TIMEOUT:
            try:
                process_status = await coordinator.get_process_status(process_token)
                _LOGGER.debug("Process Status - %s", process_status)
                # Do checks
                if process_status.error:
                    _LOGGER.error("Aborting process action due to process error. Error is %s", process_status.error)
                    return False

                # Set arming/disarming
                if process_status.status == "succeeded":
                    return True
            except Exception as ex:  # pylint: disable=broad-exception-caught
                _LOGGER.error("Unable to complete process action.  Error is %s", ex)
                return False

            await asyncio.sleep(2)
            timeout += 2

    @property
    def device_info(self):
        """Return device info."""
        if hasattr(self, "_device") and self._device and hasattr(self._device, "id"):
            return {
                "name": self.get_base_name(self._device),
                "identifiers": {(DOMAIN, f"{self.coordinator.panel_info.serial}-{self._device.id}")},
                "manufacturer": "Visonic",
                "model": self._device.subtype.replace("_", " ")
                if self._device.subtype != "VISONIC_PANEL"
                else self.coordinator.panel_info.model,
                "via_device": (
                    DOMAIN,
                    self.coordinator.config_entry.data[CONF_PANEL_ID],
                )
            }
        else:
            return {
                "name": "Alarm Panel",
                "identifiers": {(DOMAIN, f"{self.coordinator.config_entry.data[CONF_PANEL_ID]}")},
                "manufacturer": "Visonic",
                "model": self.coordinator.panel_info.model
            }
