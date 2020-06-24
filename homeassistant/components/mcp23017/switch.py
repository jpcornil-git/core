"""Support for switch sensor using I2C MCP23017 chip."""
import logging

import voluptuous as vol

from homeassistant.components.mcp23017 import mcp23017
from homeassistant.components.switch import PLATFORM_SCHEMA
from homeassistant.const import DEVICE_DEFAULT_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import ToggleEntity

_LOGGER = logging.getLogger(__name__)

CONF_INVERT_LOGIC = "invert_logic"
CONF_I2C_ADDRESS = "i2c_address"
CONF_PINS = "pins"
CONF_PULL_MODE = "pull_mode"

DEFAULT_INVERT_LOGIC = False
DEFAULT_I2C_ADDRESS = 0x20

_SWITCHES_SCHEMA = vol.Schema({cv.positive_int: cv.string})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PINS): _SWITCHES_SCHEMA,
        vol.Optional(CONF_INVERT_LOGIC, default=DEFAULT_INVERT_LOGIC): cv.boolean,
        vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): vol.Coerce(int),
    }
)


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the MCP23017 devices."""
    invert_logic = config.get(CONF_INVERT_LOGIC)
    i2c_address = config.get(CONF_I2C_ADDRESS)
    pins = config.get(CONF_PINS)

    device = await mcp23017.async_get_device(i2c_address)

    switches = []
    for pin_num, pin_name in pins.items():
        switches.append(MCP23017Switch(device, pin_name, pin_num, invert_logic))

    add_entities(switches)


class MCP23017Switch(ToggleEntity):
    """Representation of a  MCP23017 output pin."""

    def __init__(self, device, name, num, invert_logic):
        """Initialize the pin."""
        self._device = device
        self._name = name or DEVICE_DEFAULT_NAME
        self._num = num
        self._invert_logic = invert_logic
        self._state = False

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    @property
    def assumed_state(self):
        """Return true if optimistic updates are used."""
        return True

    async def async_added_to_hass(self):
        """Handle entity about to be added to hass event."""
        await super().async_added_to_hass()
        await self._device.async_setup_output(self._pin) 

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        await self._device.async_write_output(self._pin, not self._invert_logic)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self._device.async_write_output(self._pin, self._invert_logic)
        self._state = False
        self.async_write_ha_state()
