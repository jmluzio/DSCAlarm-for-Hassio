import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CODE, CONF_EMAIL, CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_UUID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyvisonicalarm import alarm as VisonicAlarm
from pyvisonicalarm.classes import Event as VisonicEvent
from pyvisonicalarm.classes import Panel as VisonicPanel
from pyvisonicalarm.classes import Partition as VisonicPartitionStatus
from pyvisonicalarm.classes import PanelInfoPartition as VisonicPartitionInfo
from pyvisonicalarm.classes import Status as VisonicStatus
from pyvisonicalarm.devices import Device as VisonicDevice
from pyvisonicalarm.exceptions import UnauthorizedError, UserAuthRequiredError

from .const import (
    CONF_PANEL_ID,
    CONF_PIN_REQUIRED_ARM,
    CONF_PIN_REQUIRED_DISARM,
    DEFAUL_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class VisonicAlarmData:
    """Data store for alarm data."""

    devices: list[VisonicDevice] = None
    panel_info: VisonicPanel = None
    status: VisonicStatus = None

class VisonicAlarmCoordinator(DataUpdateCoordinator):
    """Data update coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize data update coordinator."""
        self.scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, DEFAUL_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=self.scan_interval),
        )

        self.alarm_data = VisonicAlarmData()
        self.last_update = datetime.now()
        self.alarm: VisonicAlarm.Setup = None
        self.alarm.arm_stay = arm_stay
        self.events: list[VisonicEvent] = []
        self.panel_info: VisonicPanel = None
        self.status: VisonicStatus = None
        self.devices: list[VisonicDevice] = []
        self.pin_required_arm = config_entry.options.get(CONF_PIN_REQUIRED_ARM, True)
        self.pin_required_disarm = config_entry.options.get(CONF_PIN_REQUIRED_DISARM, True)

    async def validate_logged_in(self):
        """Validate logged in to account"""
        if not self.alarm:
            _LOGGER.debug("Initiating Visonic API")
            self.alarm = await self.hass.async_add_executor_job(
                VisonicAlarm.Setup,
                self.config_entry.data[CONF_HOST],
                self.config_entry.data[CONF_UUID],
            )
            _LOGGER.debug(
                "Supported rest versions: %s", await self.hass.async_add_executor_job(self.alarm.get_rest_versions)
            )
            await self.hass.async_add_executor_job(self.alarm.set_rest_version)

        try:
            await self.hass.async_add_executor_job(self.alarm.api.is_logged_in)
            return True
        except (UserAuthRequiredError, UnauthorizedError):
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
                self.panel_info = await self.hass.async_add_executor_job(self.alarm.get_panel_info)
                return True
            except Exception as ex:  # pylint: disable=broad-exception-caught
                _LOGGER.error("Unable to connect to alarm panel.  Error is - %s", ex)
                return False

    async def async_update_data(self):
        """Update all alarm statuses."""
        try:
            if await self.validate_logged_in():
                self.status = await self.hass.async_add_executor_job(self.alarm.get_status)
                self.panel_info = await self.hass.async_add_executor_job(self.alarm.get_panel_info)
                self.devices = await self.hass.async_add_executor_job(self.alarm.get_devices)
                self.last_update = datetime.now()
        except Exception as ex:
            _LOGGER.error("Update failed: %s", ex)
            raise

        return True

    async def async_update_status(self):
        """Update alarm status."""
        try:
            if await self.validate_logged_in():
                self.status = await self.hass.async_add_executor_job(self.alarm.get_status)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Status update failed. Error is - %s", ex)

    async def get_process_status(self, process_token):
        """Get status of command process."""
        process_status = await self.hass.async_add_executor_job(self.alarm.get_process_status, process_token)
        if process_status:
            return process_status[0]

    def get_partition_info_by_id(self, partition_id) -> VisonicPartitionInfo:
        """Get status of partition."""
        if self.status and partition_id in [partition.id for partition in self.panel_info.partitions]:
            return next(partition for partition in self.panel_info.partitions if partition.id == partition_id)

    def get_partition_status_by_id(self, partition_id) -> VisonicPartitionStatus:
        """Get status of partition."""
        if self.status and partition_id in [partition.id for partition in self.status.partitions]:
            return next(partition for partition in self.status.partitions if partition.id == partition_id)

    def get_device_by_id(self, device_id: int) -> VisonicDevice | None:
        """Get device by device id."""
        if not self.devices:
            return None
        for device in self.devices:
            if device.id == device_id:
                return device
