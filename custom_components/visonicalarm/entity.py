import logging
import asyncio
from .const import PROCESS_TIMEOUT, SENSOR_TYPE_FRIENDLY_NAME

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
