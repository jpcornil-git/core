"""Support for I2C LPS22HB Pressure sensor."""
import logging
import threading

# LPS22HB Register Map
R_INTERRUPT_CFG = 0x0B
R_THS_P_L = 0x0C
R_THS_P_H = 0x0D
R_WHO_AM_I = 0x0F
R_CTRL_REG1 = 0x10
R_CTRL_REG2 = 0x11
R_CTRL_REG3 = 0x12
R_FIFO_CTRL = 0x14
R_REF_P_XL = 0x15
R_REF_P_L = 0x16
R_REF_P_H = 0x17
R_RPDS_L = 0x18
R_RPDS_H = 0x19
R_RES_CONF = 0x1A
R_INT_SOURCE = 0x25
R_FIFO_STATUS = 0x26
R_STATUS = 0x27
R_PRESS_OUT_XL = 0x28
R_PRESS_OUT_L = 0x29
R_PRESS_OUT_H = 0x2A
R_TEMP_OUT_L = 0x2B
R_TEMP_OUT_H = 0x2C
R_LPFP_RES = 0x33

_LOGGER = logging.getLogger(__name__)


class LPS22HB:
    """LPS22HB device driver."""

    def __init__(self, bus, address):
        """Create a LPS22HB instance at {address} on I2C {bus}."""
        self._bus = bus
        self._address = address

        self._device_lock = threading.Lock()
        self._sensor_callbacks = dict()

        device_id = self[R_WHO_AM_I]
        if device_id != 0xB1:
            # FIXME: Should we bail out somehow here ... ?
            _LOGGER.warning(
                "%s @ 0x%02x, bad device identification ()",
                type(self).__name__,
                address,
                device_id,
            )

        # Set 1Hz conversion rate [6:4], enable i/20 filter [3:2] make msb-lsb reading atomic [1]
        self[R_CTRL_REG1] = (1 << 4) + (0x3 << 2) + (0x1 << 1)

        _LOGGER.info("%s @ 0x%02x device created", type(self).__name__, address)

    def __enter__(self):
        """Lock access to device (with statement)."""
        self._device_lock.acquire()
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        """Unlock access to device (with statement)."""
        self._device_lock.release()
        return False

    def __setitem__(self, register, value):
        """Set LPS22HB {register} to {value}."""
        self._bus.write_byte_data(self._address, register, value)

    def __getitem__(self, register):
        """Get value of LPS22HB {register}."""
        data = self._bus.read_byte_data(self._address, register)
        return data

    @property
    def address(self):
        """Return device address."""
        return self._address

    # -- Sensor function(s)

    def get_pressure(self):
        """Read pressure data.

        Access should be protected by a with statement to avoid threading issues.
        """
        # Read pressure value
        pressure = (
            (self[R_PRESS_OUT_H] << 16)
            + (self[R_PRESS_OUT_L] << 8)
            + self[R_PRESS_OUT_XL]
        )
        pressure -= (1 << 24) if (pressure & 0x800000) else 0

        return float(pressure) / 4096.0

    def get_temperature(self):
        """Read temperature data.

        Access should be protected by a with statement to avoid threading issues.
        """
        # Read temperature value
        temperature = (self[R_TEMP_OUT_H] << 8) + self[R_TEMP_OUT_L]
        temperature -= (1 << 16) if (temperature & 0x8000) else 0

        return float(temperature) / 100.0

    # -- Called from async thread pool

    def register_sensor_callback(self, sensor_name, sensor_function, callback):
        """Register callback for state change."""
        with self:
            self._sensor_callbacks[sensor_name] = {
                "sensor_function": sensor_function,
                "callback": callback,
            }

    # -- Called from bus manager thread

    def run(self):
        """Poll sensor data and call corresponding callback if it exists."""
        with self:
            for entry in self._sensor_callbacks.values():
                # Fetch data
                value = entry["sensor_function"]()
                # Call callback function with value
                entry["callback"](value)
