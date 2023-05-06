"""
Interfaces with the Visonic Alarm control panel.
"""
import asyncio
import logging
from datetime import timedelta
from .entity import BaseVisonicEntity

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
import homeassistant.components.persistent_notification as pn
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_DISARMED,
    STATE_UNKNOWN,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMING,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
    CONF_CODE,
)
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.components.alarm_control_panel.const import (
    CodeFormat,
    AlarmControlPanelEntityFeature,
)
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.system_info import async_get_system_info
from homeassistant.exceptions import HomeAssistantError, Unauthorized, UnknownUser

from . import CONF_USER_CODE, CONF_EVENT_HOUR_OFFSET, CONF_NO_PIN_REQUIRED
from .const import CONF_PANEL_ID, DOMAIN, DATA, PROCESS_TIMEOUT

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

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Visonic Alarm platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    visonic_alarm = [VisonicAlarm(coordinator, hass)]
    async_add_entities(visonic_alarm)

    # Create an event listener to listen for changed arm state.
    # We will only fetch the events from the API once the arm state has changed
    # because it is quite a lot of data.
    """
    def arm_event_listener(event):
        entity_id = event.data.get('entity_id')
        old_state = event.data.get('old_state')
        new_state = event.data.get('new_state')

        if new_state is None or new_state.state in (STATE_UNKNOWN, ''):
            return None

        if entity_id == 'alarm_control_panel.visonic_alarm' and \
                old_state.state is not new_state.state:
            state = new_state.state
            if state == 'armed_home' or state == 'armed_away' or \
                    state == 'Disarmed':
                last_event = coordinator.alarm.get_last_event(
                    timestamp_hour_offset=visonic_alarm.event_hour_offset)
                visonic_alarm.update_last_event(last_event['user'],
                                                last_event['timestamp'])

    #hass.bus.listen(EVENT_STATE_CHANGED, arm_event_listener)
    """


class AlarmAction:
    DISARM = "DISARM"
    ARM_HOME = "ARM_HOME"
    ARM_AWAY = "ARM_AWAY"


AlarmEndState = {
    "DISARM": "DISARM",
    "ARM_HOME": "HOME",
    "ARM_AWAY": "AWAY",
}


class AlarmStatus:
    EXIT = "EXIT"
    ENTRYDELAY = "ENTRYDELAY"
    ALARM = "ALARM"


class AlarmState:
    DISARM = "DISARM"
    AWAY = "AWAY"
    HOME = "HOME"


AlarmState1 = {
    "AWAY": STATE_ALARM_ARMED_AWAY,
    "HOME": STATE_ALARM_ARMED_HOME,
    "DISARM": STATE_ALARM_DISARMED,
    "DISARMING": STATE_ALARM_DISARMING,
    "ARMING": STATE_ALARM_ARMING,
    "PENDING": STATE_ALARM_PENDING,
    "ALARM": STATE_ALARM_TRIGGERED,
    "EXIT": STATE_ALARM_PENDING,
}


class Status:
    SUCCESS = 0
    FAILED = 1


class VisonicAlarm(BaseVisonicEntity, AlarmControlPanelEntity, CoordinatorEntity):
    """Representation of a Visonic Alarm control panel."""

    def __init__(self, coordinator, hass):
        """Initialize the Visonic Alarm panel."""
        super().__init__(coordinator)
        self._hass = hass
        self.coordinator = coordinator
        self._alarm = self.coordinator.alarm
        self._code = self.coordinator.config_entry.data[CONF_CODE]
        self._partition = self.coordinator.get_partition_status(
            self.coordinator._partition_id
        )
        self._changed_by = None
        self._changed_timestamp = None
        self._event_hour_offset = self.coordinator.config_entry.data.get(
            CONF_EVENT_HOUR_OFFSET, 0
        )
        # self._disarming = False
        # self._transaction_in_progress = False
        self._arm_in_progress = False
        self._disarm_in_progress = False
        self._partition_id = coordinator._partition_id
        self._state = self.get_partition_state(self._partition)

    @property
    def name(self):
        """Return the name of the device."""
        return f"Alarm Panel {self.coordinator.panel_info.serial}"

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self.coordinator.panel_info.serial}-panel"

    @property
    def state_attributes(self):
        """Return the state attributes of the alarm system."""
        attrs = super().state_attributes
        attrs[ATTR_SYSTEM_SERIAL_NUMBER] = self.coordinator.panel_info.serial
        attrs[ATTR_SYSTEM_MODEL] = self.coordinator.panel_info.model
        attrs[ATTR_SYSTEM_READY] = self.coordinator.get_partition_status(
            self.coordinator._partition_id
        ).ready
        # ATTR_SYSTEM_CONNECTED: self._alarm.connected(),
        # ATTR_SYSTEM_SESSION_TOKEN: self._alarm.session_token,
        attrs[ATTR_SYSTEM_LAST_UPDATE] = self.coordinator._last_update
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
        if (
            self.coordinator.pin_required_arm and self._state == STATE_ALARM_DISARMED
        ) or (
            self.coordinator.pin_required_disarm
            and self._state in [STATE_ALARM_ARMED_HOME, STATE_ALARM_ARMED_AWAY]
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
        _LOGGER.debug(f"Alarm update initiated by {self.name}")
        if delay:
            await asyncio.sleep(delay)
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._partition = self.coordinator.get_partition_status(
            self.coordinator._partition_id
        )
        self._state = self.get_partition_state(self._partition)
        self.async_write_ha_state()

    def get_partition_state(self, partition) -> str | None:
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
        if self.coordinator.pin_required_disarm:
            if code != self._code:
                raise HomeAssistantError(
                    f"Pin is required to disarm this alarm but no pin was provided"
                )

        process_token = await self.hass.async_add_executor_job(self._alarm.disarm)
        self._disarm_in_progress = True
        self._state = STATE_ALARM_DISARMING
        self.async_write_ha_state()

        if await self.async_wait_for_process_success(self.coordinator, process_token):
            self._disarm_in_progress = False
            await self.async_force_update()
        else:
            _LOGGER.error(f"Alarm disarming did not complete successfully.")

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        await self.async_alarm_arm(AlarmAction.ARM_HOME, code)

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        await self.async_alarm_arm(AlarmAction.ARM_AWAY, code)

    async def async_alarm_arm(self, action: AlarmAction, code):
        if self.coordinator.pin_required_arm and code != self._code:
            raise HomeAssistantError(
                f"Pin is required to arm this alarm but no pin was provided"
            )

        # Get current status of partition
        await self.coordinator.async_update_status()
        partition = self.coordinator.get_partition_status(self._partition_id)

        if partition.ready:
            try:
                if action == AlarmAction.ARM_HOME:
                    process_token = await self.hass.async_add_executor_job(
                        self._alarm.arm_home
                    )
                elif action == AlarmAction.ARM_AWAY:
                    process_token = await self.hass.async_add_executor_job(
                        self._alarm.arm_away
                    )

                self._arm_in_progress = True
                self._state = STATE_ALARM_ARMING
                self.async_write_ha_state()

                if await self.async_wait_for_process_success(
                    self.coordinator, process_token
                ):
                    self._arm_in_progress = False
                    await self.async_force_update()
                else:
                    _LOGGER.error(f"{action} did not complete successfully.")
                    raise HomeAssistantError(f"There was an error setting the alarm")

            except Exception as ex:
                _LOGGER.error(f"Unable to complete {action}.  Error is {ex}")
                raise HomeAssistantError(f"Unknown error setting the alarm")
        else:
            pn.async_create(
                self._hass,
                "The alarm system is not in a ready state. "
                "Maybe there are doors or windows open?",
                title=f"{action} Failed",
            )
