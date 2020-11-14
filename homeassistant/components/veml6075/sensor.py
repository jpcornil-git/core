"""Platform for sensor integration."""

import asyncio
import functools
import logging

import voluptuous as vol

from homeassistant.components.i2c.const import DOMAIN as DOMAIN_I2C
from homeassistant.components.sensor import DEVICE_CLASS_UV, PLATFORM_SCHEMA
from homeassistant.components.veml6075 import VEML6075
from homeassistant.const import CONF_SENSOR_TYPE, DEVICE_DEFAULT_NAME, UV_INDEX
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_I2C_ADDRESS = "i2c_address"
CONF_SCAN_SLOWDOWN = "scan_slowdown"

DEFAULT_I2C_ADDRESS = 0x10
DEFAULT_SCAN_SLOWDOWN = 100  # 10s

_SENSOR_SCHEMA = vol.Schema(
    {
        vol.In([DEVICE_CLASS_UV]): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SENSOR_TYPE): _SENSOR_SCHEMA,
        vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): vol.Coerce(int),
        vol.Optional(CONF_SCAN_SLOWDOWN, default=DEFAULT_SCAN_SLOWDOWN): vol.Coerce(
            int
        ),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the LPS22HB sensor platform."""

    # Bail out if i2c device manager is not available
    if DOMAIN_I2C not in hass.data:
        _LOGGER.warning(
            "Unable to setup %s sensor (missing %s platform)",
            DOMAIN,
            DOMAIN_I2C,
        )
        return

    sensor_devices = config[CONF_SENSOR_TYPE]
    scan_slowdown = config[CONF_SCAN_SLOWDOWN]

    i2c_address = config[CONF_I2C_ADDRESS]
    i2c_bus = hass.data[DOMAIN_I2C]

    sensors = []
    for sensor_class, sensor_name in sensor_devices.items():
        sensor_entity = VEML6075Sensor(sensor_class, sensor_name)
        if await hass.async_add_executor_job(
            functools.partial(
                sensor_entity.bind, VEML6075, i2c_bus, i2c_address, scan_slowdown
            )
        ):
            sensors.append(sensor_entity)

    async_add_entities(sensors, False)


class VEML6075Sensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, function, name):
        """Initialize the HTS221 sensor."""
        self._name = name or DEVICE_DEFAULT_NAME
        self._device_class = function
        self._device = None
        self._state = None

        _LOGGER.info("%s(%s:'%s') created", type(self).__name__, function, name)

    @property
    def should_poll(self):
        """No polling needed from homeassistant for this entity."""
        return False

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return UV_INDEX

    @property
    def device_class(self):
        """Return the sensor device class."""
        return self._device_class

    @callback
    async def async_input_callback(self, value):
        """Update sensor state."""
        self._state = f"{value:.1f}"
        await self.async_schedule_update_ha_state()

    # Sync functions executed outside of the hass async loop

    def input_callback(self, value):
        """Signal a state change and call the async counterpart."""
        asyncio.run_coroutine_threadsafe(
            self.async_input_callback(value), self.hass.loop
        )

    def bind(self, device_class, bus, address, scan_slowdown):
        """Register a device to the given {bus, address}.

        This function should be called from the thread pool (call blocking functions).
        """
        # Bind a LPS22HB device to this binary_sensor entity
        self._device = bus.register_device(device_class, address, scan_slowdown)

        if self._device:
            sensor_function = self._device.get_uv_index

            self._device.register_sensor_callback(
                self._name, sensor_function, self.input_callback
            )

            _LOGGER.info(
                "%s(%s:'%s') bound to I2C device@0x%02x",
                type(self).__name__,
                self._device_class,
                self._name,
                address,
            )
        else:
            _LOGGER.warning(
                "Failed to bind %s(%s:'%s') to I2C device@0x%02x",
                type(self).__name__,
                self._device_class,
                self._name,
                address,
            )

        return self._device
