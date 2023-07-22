"""
Interfaces with the Visonic Alarm sensors.
"""
import asyncio
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import LIGHT_LUX, STATE_CLOSED, STATE_OPEN, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA, DOMAIN, SUPPORTED_SENSORS
from .entity import BaseVisonicEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Visonic Alarm platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA]
    sensors = []

    for device in coordinator.devices:
        _LOGGER.debug("Found: %s, %s", device.subtype, str(device.device_type))
        if device and device.subtype and device.subtype in SUPPORTED_SENSORS:
            _LOGGER.debug(
                "New device found [Type: %s %s ] [ID: %s ]",
                str(device.device_type),
                str(device.subtype),
                str(device.id),
            )

            if device.device_type == "CONTROL_PANEL":
                _LOGGER.debug("Adding panel status sensor")
                sensors.append(VisonicStatusSensor(coordinator, coordinator.status))
                continue

            sensors.append(VisonicAlarmSensor(coordinator, device, "state"))

            if hasattr(device, "temperature"):
                sensors.append(VisonicAlarmTemperatureSensor(coordinator, device, "temperature"))

            if hasattr(device, "brightness"):
                sensors.append(VisonicAlarmLuxSensor(coordinator, device, "brightness"))

    async_add_entities(sensors)


class VisonicAlarmSensor(BaseVisonicEntity, CoordinatorEntity, SensorEntity):
    """Implementation of a Visonic Alarm Contact sensor."""

    def __init__(self, coordinator, device, sensor_type=None, status=None):
        """Initialize the sensor"""
        super().__init__(coordinator)
        self._device = device
        self._alarm = coordinator
        self._sensor_type = sensor_type
        self._status = status

    def get_attrs(self, defined_attrs: list) -> dict:
        """Return attributes for sensor."""
        attrs = {}
        for attr in defined_attrs:
            if hasattr(self._device, attr):
                attrs[attr] = getattr(self._device, attr)
        return attrs

    @property
    def name(self):
        """Return the name of the sensor"""
        if self._sensor_type:
            return f"{self.get_base_name(self._device)} {str(self._sensor_type).capitalize()}"

        return self.get_base_name(self._device)

    @property
    def unique_id(self):
        """Return unique id."""
        return f"{DOMAIN}-{self._alarm.panel_info.serial}-{self._device.id}{self._sensor_type}"

    @property
    def state_attributes(self):
        """Return the state attributes of the alarm system."""
        defined_attrs = ["location", "name", "device_type", "subtype", "zone_type"]
        return self.get_attrs(defined_attrs)

    @property
    def icon(self):
        """Return icon"""
        icon = None
        if self.state == STATE_CLOSED:
            icon = "mdi:door-closed"
        elif self.state == STATE_OPEN:
            icon = "mdi:door-open"
        return icon

    @property
    def state(self):
        """Return the state of the sensor."""
        return getattr(self._device, self._sensor_type) if hasattr(self._device, self._sensor_type) else "Unknown"

    async def async_force_update(self, delay: int = 0):
        """Force update of sensor."""
        _LOGGER.debug("Alarm update initiated by %s", self.name)
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
            _LOGGER.warning("Could not update the device information: %s", error)


class VisonicAlarmTemperatureSensor(VisonicAlarmSensor):
    """Class for temperature sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""
        return float(self._device.temperature)

    @property
    def state_attributes(self):
        attrs = {}
        if hasattr(self._device, "temperature_last_updated"):
            attrs["last_updated"] = self.convert_to_local_datetime(self._device.temperature_last_updated)
        return attrs

    @property
    def device_class(self):
        """Return device class."""
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self):
        """Return state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state of the entity."""
        return self.state

    @property
    def native_unit_of_measurement(self):
        """Return unit of temperature"""
        return UnitOfTemperature.CELCIUS


class VisonicAlarmLuxSensor(VisonicAlarmSensor):
    """Class for a brightness sensor"""

    @property
    def state(self):
        """Return the state of the sensor."""
        return float(self._device.brightness)

    @property
    def state_attributes(self):
        attrs = {}
        if hasattr(self._device, "brightness_last_updated"):
            attrs["last_updated"] = self.convert_to_local_datetime(self._device.brightness_last_updated)
        return attrs

    @property
    def device_class(self):
        """Return device class."""
        return SensorDeviceClass.ILLUMINANCE

    @property
    def state_class(self):
        """Return state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state of the entity."""
        return self.state

    @property
    def native_unit_of_measurement(self):
        """Return unit of brightness"""
        return LIGHT_LUX  # UnitOfTemperature.CELCIUS


class VisonicStatusSensor(VisonicAlarmSensor):
    """Class for status sensor."""

    @property
    def name(self):
        """Return the name of the sensor"""
        return "Partition Ready"

    @property
    def unique_id(self):
        return f"{DOMAIN}-{self._alarm.panel_info.serial}-{self.name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._device.partitions[0].ready

    @property
    def state_attributes(self):
        return {}

    @property
    def native_value(self):
        """Return the state of the entity."""
        return self.state

    async def async_force_update(self, delay: int = 0):
        _LOGGER.debug("Alarm update initiated by %s", self.name)
        if delay:
            await asyncio.sleep(delay)
        await self.coordinator.async_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the latest data"""
        try:
            self._device = self.coordinator.status
            self.async_write_ha_state()

        except OSError as error:
            _LOGGER.warning("Could not update the device information: %s", error)
