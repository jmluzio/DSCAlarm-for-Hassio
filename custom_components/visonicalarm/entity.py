from datetime import datetime
from dateutil import tz
import logging
import asyncio
from .const import CONF_PANEL_ID, DOMAIN, PROCESS_TIMEOUT, SENSOR_TYPE_FRIENDLY_NAME

_LOGGER = logging.getLogger(__name__)


class BaseVisonicEntity:
    @staticmethod
    def get_base_name(device=None):
        if not device:
            return "Alarm Panel"
        if device.subtype in SENSOR_TYPE_FRIENDLY_NAME:
            name = f"{SENSOR_TYPE_FRIENDLY_NAME[device.subtype]}"
        else:
            name = f"{device.subtype}"

        if hasattr(device, "location") and device.location:
            name = f"{device.location} {name}"

        if SENSOR_TYPE_FRIENDLY_NAME[device.subtype] == "Keyfob":
            if hasattr(device, "owner_name"):
                name = f"{name} {device.owner_name}"
            else:
                name = f"{name} {device.device_number}"

        return name

    def convert_to_local_datetime(self, dt: datetime) -> datetime:
        utc = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        utc = utc.replace(tzinfo=tz.tzutc())
        return utc.astimezone(tz.tzlocal())

    async def async_wait_for_process_success(self, coordinator, process_token) -> bool:
        timeout = 0
        while timeout <= PROCESS_TIMEOUT:
            try:
                process_status = await coordinator.get_process_status(process_token)
                _LOGGER.debug(f"Process Status - {process_status}")
                # Do checks
                if process_status.error:
                    _LOGGER.error(
                        f"Aborting action due to process error. Error is {process_status.error}"
                    )
                    return False

                # Set arming/disarming
                if process_status.status == "succeeded":
                    return True
            except Exception as ex:
                _LOGGER.error(f"Unable to complete process action.  Error is {ex}")
                return False

            await asyncio.sleep(2)
            timeout += 2

    @property
    def device_info(self):
        if hasattr(self, "_device") and self._device and hasattr(self._device, "id"):
            return {
                "name": self.get_base_name(self._device),
                "identifiers": {
                    (DOMAIN, f"{self.coordinator.panel_info.serial}-{self._device.id}")
                },
                "manufacturer": "Visonic",
                "model": self._device.subtype.replace("_", " ")
                if self._device.subtype != "VISONIC_PANEL"
                else self.coordinator.panel_info.model,
                "serial_number": self._device.id,
                "product_type": self._device.subtype,
                "product_identifier": self._device.id,
                "via_device": (
                    DOMAIN,
                    self.coordinator.config_entry.data[CONF_PANEL_ID],
                ),
            }
        else:
            return {
                "name": f"Alarm Panel",
                "identifiers": {
                    (DOMAIN, f"{self.coordinator.config_entry.data[CONF_PANEL_ID]}")
                },
                "manufacturer": "Visonic",
                "model": self.coordinator.panel_info.model,
                "serial_number": self.coordinator.panel_info.serial,
                "product_type": "Alarm Panel",
                "product_identifier": self.coordinator.panel_info.model,
            }
