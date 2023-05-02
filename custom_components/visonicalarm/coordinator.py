from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
from pyvisonicalarm import alarm as VisonicAlarm
from pyvisonicalarm.devices import Device as VisonicDevice
from pyvisonicalarm.classes import (
    Status as VisonicStatus,
    Panel as VisonicPanel,
    Partition as VisonicPartition,
    Event as VisonicEvent,
)
from pyvisonicalarm.exceptions import UserAuthRequiredError, UnauthorizedError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_CODE,
    CONF_UUID,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_PIN_REQUIRED_ARM,
    CONF_PIN_REQUIRED_DISARM,
    DEFAUL_SCAN_INTERVAL,
    DOMAIN,
    CONF_PANEL_ID,
    CONF_PARTITION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class VisonicAlarmData:
    devices: list[VisonicDevice] = None
    panel_info: VisonicPanel = None
    status: VisonicStatus = None


class VisonicAlarmCoordinator(DataUpdateCoordinator):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize data update coordinator."""
        self.scan_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAUL_SCAN_INTERVAL
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=self.scan_interval),
        )

        self.alarm_data = VisonicAlarmData()
        self._last_update = datetime.now()

        self._partition_id = config_entry.data[CONF_PARTITION]
        self.alarm: VisonicAlarm.Setup = None
        self.events: list[VisonicEvent] = []
        self.panel_info: VisonicPanel = None
        self.status: VisonicStatus = None
        self.devices: list[VisonicDevice] = []
        self.pin_required_arm = config_entry.options.get(CONF_PIN_REQUIRED_ARM, True)
        self.pin_required_disarm = config_entry.options.get(
            CONF_PIN_REQUIRED_DISARM, True
        )

    async def validate_logged_in(self):
        if not self.alarm:
            _LOGGER.debug("Initiating Visonic API")
            self.alarm = await self.hass.async_add_executor_job(
                VisonicAlarm.Setup,
                self.config_entry.data[CONF_HOST],
                self.config_entry.data[CONF_UUID],
            )

        try:
            await self.hass.async_add_executor_job(self.alarm.api.is_logged_in)
            return True
        except (UserAuthRequiredError, UnauthorizedError) as ex:
            _LOGGER.debug("Not logged in - so do it now!")
            try:
                await self.hass.async_add_executor_job(
                    self.alarm.authenticate,
                    self.config_entry.data[CONF_EMAIL],
                    self.config_entry.data[CONF_PASSWORD],
                )
                await self.hass.async_add_executor_job(
                    self.alarm.panel_login,
                    self.config_entry.data[CONF_PANEL_ID],
                    self.config_entry.data[CONF_CODE],
                )
                self.panel_info = await self.hass.async_add_executor_job(
                    self.alarm.get_panel_info
                )
                return True
            except Exception as ex:
                _LOGGER.error(f"Unable to connect to alarm panel.  Error is - {ex}")
                return False

    async def async_update_data(self):
        """Update all alarm statuses."""
        try:
            if await self.validate_logged_in():
                self.status = await self.hass.async_add_executor_job(
                    self.alarm.get_status
                )
                self.panel_info = await self.hass.async_add_executor_job(
                    self.alarm.get_panel_info
                )
                self.devices = await self.hass.async_add_executor_job(
                    self.alarm.get_devices
                )
                self._last_update = datetime.now()
        except Exception as ex:
            _LOGGER.error("Update failed: %s", ex)
            raise

        return True

    async def async_update_status(self):
        try:
            if await self.validate_logged_in():
                self.status = await self.hass.async_add_executor_job(
                    self.alarm.get_status
                )
        except Exception as ex:
            _LOGGER.error(f"Status update failed. Error is - {ex}")

    async def get_process_status(self, process_token):
        process_status = await self.hass.async_add_executor_job(
            self.alarm.get_process_status, process_token
        )
        if process_status:
            return process_status[0]

    def get_partition_status(self, partition_id) -> VisonicPartition:
        if self.status and partition_id in [
            partition.id for partition in self.status.partitions
        ]:
            return next(
                partition
                for partition in self.status.partitions
                if partition.id == partition_id
            )

    def get_device_by_id(self, device_id: int) -> VisonicDevice | None:
        if not self.devices:
            return None
        for device in self.devices:
            if device.id == device_id:
                return device
