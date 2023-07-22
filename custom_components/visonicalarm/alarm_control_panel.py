"""
Interfaces with the Visonic Alarm control panel.
"""
import asyncio
import logging

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelEntityFeature, CodeFormat
from homeassistant.const import (
    CONF_CODE,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA, DOMAIN
from .entity import BaseVisonicEntity

SUPPORT_VISONIC = (
    AlarmControlPanelEntityFeature.ARM_HOME
    | AlarmControlPanelEntityFeature.ARM_AWAY
    | AlarmControlPanelEntityFeature.TRIGGER
)

_LOGGER = logging.getLogger(__name__)

ATTR_SYSTEM_SERIAL_NUMBER = "serial_number"
ATTR_SYSTEM_MODEL = "model"
ATTR_SYSTEM_READY = "ready"
ATTR_SYSTEM_CONNECTED = "connected"
ATTR_SYSTEM_SESSION_TOKEN = "session_token"
ATTR_SYSTEM_LAST_UPDATE = "last_update"
ATTR_CHANGED_BY = "changed_by"
ATTR_CHANGED_TIMESTAMP = "changed_timestamp"
ATTR_ALARMS = "alarm"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Visonic Alarm platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    visonic_alarm = [VisonicAlarm(coordinator, hass)]
    async_add_entities(visonic_alarm)


class AlarmAction:
    """Alarm Actions"""

    DISARM = "DISARM"
    ARM_HOME = "ARM_HOME"
    ARM_AWAY = "ARM_AWAY"


class AlarmStatus:
    """Alarm Status"""

    EXIT = "EXIT"
    ENTRYDELAY = "ENTRYDELAY"
    ALARM = "ALARM"


class AlarmState:
    """Alarm State"""

    DISARM = "DISARM"
    AWAY = "AWAY"
    HOME = "HOME"


class VisonicAlarm(BaseVisonicEntity, AlarmControlPanelEntity, CoordinatorEntity):
    """Representation of a Visonic Alarm control panel."""

    def __init__(self, coordinator, hass):
        """Initialize the Visonic Alarm panel."""
        super().__init__(coordinator)
        self._hass = hass
        self.coordinator = coordinator
        self._alarm = self.coordinator.alarm
        self._code = self.coordinator.config_entry.data[CONF_CODE]
        self._partition = self.coordinator.get_partition_status(self.coordinator.partition_id)
        self._changed_by = None
        self._changed_timestamp = None
        self._arm_in_progress = False
        self._disarm_in_progress = False
        self.partition_id = coordinator.partition_id
        self._state = self.get_partition_state(self._partition)

    @property
    def name(self):
        """Return the name of the device."""
        return f"Alarm Panel {self.coordinator.panel_info.serial}"

    @property
    def unique_id(self):
        """Return unique id."""
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-panel"

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the alarm system."""
        attrs = super().state_attributes
        attrs[ATTR_SYSTEM_SERIAL_NUMBER] = self.coordinator.panel_info.serial
        attrs[ATTR_SYSTEM_MODEL] = self.coordinator.panel_info.model
        attrs[ATTR_SYSTEM_READY] = self.coordinator.get_partition_status(self.coordinator.partition_id).ready
        # ATTR_SYSTEM_CONNECTED: self._alarm.connected(),
        # ATTR_SYSTEM_SESSION_TOKEN: self._alarm.session_token,
        attrs[ATTR_SYSTEM_LAST_UPDATE] = self.coordinator.last_update
        # ATTR_CODE_FORMAT: self.code_format,
        # ATTR_CHANGED_BY: self.changed_by,
        # ATTR_CHANGED_TIMESTAMP: self._changed_timestamp,
        # ATTR_ALARMS: self._alarm.alarm,
        return attrs

    @property
    def icon(self):
        """Return icon"""
        if self._state == STATE_ALARM_ARMED_AWAY:
            return "mdi:shield-lock"
        elif self._state == STATE_ALARM_ARMED_HOME:
            return "mdi:shield-home"
        elif self._state == STATE_ALARM_DISARMED:
            return "mdi:shield-check"
        elif self._state == STATE_ALARM_ARMING:
            return "mdi:shield-outline"
        else:
            return "hass:bell-ring"

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one or more digits/characters."""
        if (self.coordinator.pin_required_arm and self._state == STATE_ALARM_DISARMED) or (
            self.coordinator.pin_required_disarm and self._state in [STATE_ALARM_ARMED_HOME, STATE_ALARM_ARMED_AWAY]
        ):
            return CodeFormat.NUMBER

    @property
    def changed_by(self):
        """Return the last change triggered by."""
        return self._changed_by

    @property
    def changed_timestamp(self):
        """Return the last change triggered by."""
        return self._changed_timestamp

    async def async_force_update(self, delay: int = 0):
        """Force update from api"""
        _LOGGER.debug("Alarm update initiated by %s", self.name)
        if delay:
            await asyncio.sleep(delay)
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._partition = self.coordinator.get_partition_status(self.coordinator.partition_id)
        self._state = self.get_partition_state(self._partition)
        self.async_write_ha_state()

    def get_partition_state(self, partition) -> str | None:
        """Get current state of partition"""
        status = partition.status
        state = partition.state

        if self._disarm_in_progress:
            return STATE_ALARM_DISARMING

        if self._arm_in_progress:
            return STATE_ALARM_ARMING

        if status:
            if status == AlarmStatus.EXIT:
                return STATE_ALARM_ARMING
            elif status == AlarmStatus.ENTRYDELAY:
                return STATE_ALARM_PENDING
            elif status == AlarmStatus.ALARM:
                return STATE_ALARM_TRIGGERED
        else:
            if state == AlarmState.AWAY:
                return STATE_ALARM_ARMED_AWAY
            elif state == AlarmState.HOME:
                return STATE_ALARM_ARMED_HOME
            elif state == AlarmState.DISARM:
                return STATE_ALARM_DISARMED
            elif state == AlarmStatus.ALARM:
                return STATE_ALARM_TRIGGERED

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORT_VISONIC

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        _LOGGER.debug("Disarming alarm...")
        if self.coordinator.pin_required_disarm:
            if code != self._code:
                raise HomeAssistantError("Pin is required to disarm this alarm but no pin was provided")

        process_token = await self.hass.async_add_executor_job(self._alarm.disarm)
        self._disarm_in_progress = True
        self._state = STATE_ALARM_DISARMING
        self.async_write_ha_state()

        if await self.async_wait_for_process_success(self.coordinator, process_token):
            _LOGGER.debug("Disarming alarm completed successfully")
            self._disarm_in_progress = False
            await self.async_force_update()
        else:
            _LOGGER.error("Disarming alarm did not complete successfully.")

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        await self.async_alarm_arm(AlarmAction.ARM_HOME, code)

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        await self.async_alarm_arm(AlarmAction.ARM_AWAY, code)

    async def async_alarm_arm(self, action: AlarmAction, code):
        """Arm Alarm"""
        _LOGGER.debug("Arming alarm...")
        if self.coordinator.pin_required_arm and code != self._code:
            raise HomeAssistantError("Pin is required to arm this alarm but no pin was provided")

        # Get current status of partition
        await self.coordinator.async_update_status()
        partition = self.coordinator.get_partition_status(self.partition_id)

        if partition.ready:
            try:
                if action == AlarmAction.ARM_HOME:
                    process_token = await self.hass.async_add_executor_job(self._alarm.arm_home)
                elif action == AlarmAction.ARM_AWAY:
                    process_token = await self.hass.async_add_executor_job(self._alarm.arm_away)

                self._arm_in_progress = True
                self._state = STATE_ALARM_ARMING
                self.async_write_ha_state()

                if await self.async_wait_for_process_success(self.coordinator, process_token):
                    _LOGGER.debug("Arming alarm completed successfully")
                    self._arm_in_progress = False
                    await self.async_force_update()
                else:
                    self._arm_in_progress = False
                    _LOGGER.error("%s did not complete successfully.", action)
                    raise HomeAssistantError("There was an error setting the alarm")

            except HomeAssistantError:
                pass
            except Exception as ex:
                _LOGGER.error("Unable to complete %s.  Error is %s", action, ex)
                raise HomeAssistantError("Unknown error setting the alarm") from ex
        else:
            raise HomeAssistantError(
                "The alarm system is not in a ready state. Maybe there are doors or windows open?"
            )
