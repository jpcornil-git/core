"""Support for I2C MCP23017 chip."""
#FIXME: Change dictionary sting into constant
#FIXME: Validate function inputs
import logging
import asyncio

import board  # pylint: disable=import-error
import busio  # pylint: disable=import-error
import digitalio  # pylint: disable=import-error
from adafruit_mcp230xx.mcp23017 import MCP23017 as component
from functools import partial

DOMAIN = "mcp23017"

_LOGGER = logging.getLogger(__name__)


class mcp23017_device:
    def __init__(self, bus, i2c_address):
        self._lock = asyncio.Lock()
        self._instance = MCP23017(bus, address=i2c_address)
       _LOGGER.info("%s (i2c=0x%02x) device created" % (DOMAIN, i2c_address))

    def setup_output(self, device, pin):
        self._instance.direction = digitalio.Direction.OUTPUT
        self._instance.value = self._invert_logic

    def setup_input(self, device, pin):
        self._instance.direction = digitalio.Direction.INPUT
        self._instance.pull = digitalio.Pull.UP

    def write_output(self._pin, value):
        self._instance.value = value

    def read_input(self):

async def async_get_device(i2c_address):
    devices_data = hass.data[DOMAIN]

    async with devices_data['lock']:
        if i2c_address not in devices_data['address']:
            devices_data['address'][i2c_address] =  await hass.async_add_executor_job(
                partial(mcp23017_device, devices_data['bus'], i2c_address)
            )
   
            mcp.get_pin(pin_num)
    return devices['address']['i2c_address']

async def async_setup(hass, config)
    _LOGGER.info("async_setup: config = %s" % config)

    hass.data[DOMAIN]=dict()
    hass.data[DOMAIN]['lock'] = asyncio.Lock()
    hass.data[DOMAIN]['bus'] = await hass.async_add_executor_job(
        partial(busio.I2C, board.SCL, board.SDA)
    )
    hass.data[DOMAIN]['address'] = {}

   return True
