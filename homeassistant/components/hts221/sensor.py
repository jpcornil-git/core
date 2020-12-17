"""Platform for sensor integration."""

import asyncio
import functools
import logging

import voluptuous as vol

from homeassistant.components.hts221 import HTS221
from homeassistant.components.i2c.const import DOMAIN as DOMAIN_I2C
from homeassistant.components.sensor import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_TEMPERATURE,
    PLATFORM_SCHEMA,
)
from homeassistant.const import (
    CONF_SENSOR_TYPE,
    DEVICE_DEFAULT_NAME,
    PERCENTAGE,
    TEMP_CELSIUS,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_I2C_ADDRESS = "i2c_address"
CONF_SCAN_SLOWDOWN = "scan_slowdown"

DEFAULT_I2C_ADDRESS = 0x5F
DEFAULT_SCAN_SLOWDOWN = 100  # 10s

_SENSOR_SCHEMA = vol.Schema(
    {
        vol.In([DEVICE_CLASS_TEMPERATURE, DEVICE_CLASS_HUMIDITY]): cv.string,
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
    """Set up the HTS221 sensor platform."""

    hass.data.setdefault(DOMAIN, {})

    i2c_address = config[CONF_I2C_ADDRESS]

    if i2c_address not in hass.data[DOMAIN]:
        try:
            bus = hass.data[DOMAIN_I2C]
            hass.data[DOMAIN][i2c_address] = await hass.async_add_executor_job(
                functools.partial(HTS221, bus, i2c_address, config[CONF_SCAN_SLOWDOWN])
            )

        except (OSError, ValueError, KeyError) as error:
            _LOGGER.error(
                "Unable to create %s device at address 0x%02x (%s)",
                DOMAIN,
                i2c_address,
                error,
            )
            return

        sensor_devices = config[CONF_SENSOR_TYPE]
        sensors = []
        for sensor_class, sensor_name in sensor_devices.items():
            sensor_entity = HTS221Sensor(hass, config, sensor_class, sensor_name)
            if await hass.async_add_executor_job(sensor_entity.configure_device):
                sensors.append(sensor_entity)

        async_add_entities(sensors, False)


class HTS221Sensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, hass, config, function, name):
        """Initialize the HTS221 sensor."""
        self._hass = hass
        self._name = name or DEVICE_DEFAULT_NAME
        self._device_class = function

        # Retrieve associated device
        self._device = self._hass.data[DOMAIN][config[CONF_I2C_ADDRESS]]
        self._state = None

        _LOGGER.info("%s(%s:'%s') created", type(self).__name__, function, name)

    @property
    def icon(self):
        """Return device icon for this entity."""
        return "mdi:chip"

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
        if self._device_class == DEVICE_CLASS_TEMPERATURE:
            return TEMP_CELSIUS
        elif self._device_class == DEVICE_CLASS_HUMIDITY:
            return PERCENTAGE
        else:
            # Should never get here given voluptuous validation
            return None

    @property
    def device_class(self):
        """Return the sensor device class."""
        return self._device_class

    @callback
    async def async_push_update(self, value):
        """Update the sensor state."""
        sValue = f"{value:.1f}"
        if self._state != sValue:
            self._state = sValue
            await self.async_schedule_update_ha_state()

    # Sync functions executed outside of the hass async loop

    def push_update(self, value):
        """Signal a state change and call the async counterpart."""
        asyncio.run_coroutine_threadsafe(self.async_push_update(value), self.hass.loop)

    def configure_device(self):
        """Attach instance to a device on the given address and configure it.

        This function should be called from the thread pool as it contains blocking functions.

        Return True when successful.
        """

        if self._device:
            # Register this HTS221 entity
            if self._device.register_entity(self):
                return True

        return False
