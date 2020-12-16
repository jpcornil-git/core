"""Support for I2C HTS221 Temperature & Humidity sensor."""
import logging
import threading

from homeassistant.components.sensor import (
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_TEMPERATURE,
)

# HTS221 Register Map
R_WHO_AM_I = 0x0F
R_AV_CONF = 0x10
R_CTRL_REG1 = 0x20
R_CTRL_REG2 = 0x21
R_CTRL_REG3 = 0x22
R_STATUS_REG = 0x27
R_HUMIDITY_OUT_L = 0x28
R_HUMIDITY_OUT_H = 0x29
R_TEMP_OUT_L = 0x2A
R_TEMP_OUT_H = 0x2B
R_H0_rH = 0x30
R_H1_rH = 0x31
R_T0_degC = 0x32
R_T1_degC = 0x33
R_T1T0_MSB = 0x35
R_H0_T0_OUT_LSB = 0x36
R_H0_T0_OUT_MSB = 0x37
R_H1_T0_OUT_LSB = 0x3A
R_H1_T0_OUT_MSB = 0x3B
R_T0_OUT_LSB = 0x3C
R_T0_OUT_MSB = 0x3D
R_T1_OUT_LSB = 0x3E
R_T1_OUT_MSB = 0x3F

_LOGGER = logging.getLogger(__name__)


class HTS221:
    """HTS221 device driver."""

    def __init__(self, bus, address, slowdown):
        """Create a HTS221 instance at {address} on I2C {bus}."""
        self._bus = bus
        self._address = address
        self._slowdown = slowdown
        self._slowdown_counter = 0

        self._device_lock = threading.Lock()
        self._entities = dict()

        device_id = self[R_WHO_AM_I]
        if device_id != 0xBC:
            # FIXME: Should we bail out somehow here ... ?
            _LOGGER.warning(
                "%s @ 0x%02x, bad device identification (0x%02x)",
                type(self).__name__,
                address,
                device_id,
            )

        # set temperature[5:3]/humidity[2:0] averaging to 16/32 respectively
        self[R_AV_CONF] = (0x3 << 3) + 0x3
        # Power up device [7], make msb-lsb reading atomic [2] and 1Hz conversion rate [1:00]
        self[R_CTRL_REG1] = (1 << 7) + (1 << 2) + 0x1

        # Read calibration data and compute scaling factors for Temperature
        T1T0_MSB = self[R_T1T0_MSB]
        T0_deg = ((T1T0_MSB & 0x3) << 8) + self[R_T0_degC]
        T1_deg = ((T1T0_MSB & 0xC) << 6) + self[R_T1_degC]

        T0_adc = (self[R_T0_OUT_MSB] << 8) + self[R_T0_OUT_LSB]
        T0_adc -= (1 << 16) if (T0_adc & 0x8000) else 0

        T1_adc = (self[R_T1_OUT_MSB] << 8) + self[R_T1_OUT_LSB]
        T1_adc -= (1 << 16) if (T1_adc & 0x8000) else 0

        self._Tref_deg = float(T0_deg) / 8.0
        self._Tref_adc = float(T0_adc)
        self._Tscale = float(T1_deg - T0_deg) / 8.0 / (T1_adc - T0_adc)

        # Read calibration data and compute scaling factors for Humidity
        H0_rH = self[R_H0_rH]
        H1_rH = self[R_H1_rH]

        H0_adc = (self[R_H0_T0_OUT_MSB] << 8) + self[R_H0_T0_OUT_LSB]
        H0_adc -= (1 << 16) if (H0_adc & 0x8000) else 0

        H1_adc = (self[R_H1_T0_OUT_MSB] << 8) + self[R_H1_T0_OUT_LSB]
        H1_adc -= (1 << 16) if (H1_adc & 0x8000) else 0

        self._Href_rH = float(H0_rH) / 2.0
        self._Href_adc = float(H0_adc)
        self._Hscale = float(H1_rH - H0_rH) / 2.0 / (H1_adc - H0_adc)

        self._bus.register_device(self)

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
        """Set HTS221 {register} to {value}."""
        self._bus.write_byte_data(self._address, register, value)

    def __getitem__(self, register):
        """Get value of HTS221 {register}."""
        data = self._bus.read_byte_data(self._address, register)
        return data

    @property
    def address(self):
        """Return device address."""
        return self._address

    def get_temperature(self):
        """Read raw temperature and correct it based on calibration data.

        Access should be protected by a with statement to avoid threading issues.
        """
        T_adc = (self[R_TEMP_OUT_H] << 8) + self[R_TEMP_OUT_L]
        T_adc -= (1 << 16) if (T_adc & 0x8000) else 0
        return self._Tref_deg + self._Tscale * (float(T_adc) - self._Tref_adc)

    def get_humidity(self):
        """Read raw humidity and correct it based on calibration data.

        Access should be protected by a with statement to avoid threading issues.
        """
        H_adc = (self[R_HUMIDITY_OUT_H] << 8) + self[R_HUMIDITY_OUT_L]
        H_adc -= (1 << 16) if (H_adc & 0x8000) else 0
        return max(
            0, min(100, self._Href_rH + self._Hscale * (float(H_adc) - self._Href_adc))
        )

    def register_entity(self, entity):
        """Register entity to this device instance."""
        with self:
            self._entities[entity.device_class] = entity

            _LOGGER.info(
                "%s('%s') attached to %s@0x%02x",
                type(entity).__name__,
                entity.device_class,
                type(self).__name__,
                self.address,
            )

        return True

    # -- Called from bus manager thread

    def run(self):
        """Poll sensor data and call corresponding callback if it exists."""
        with self:
            self._slowdown_counter -= 1
            if self._slowdown_counter > 0:
                return

            self._slowdown_counter = self._slowdown

            for (device_class, entity) in self._entities.items():
                # Fetch data and call update function
                if hasattr(entity, "push_update"):
                    # Fetch data
                    if device_class == DEVICE_CLASS_TEMPERATURE:
                        value = self.get_temperature()
                    elif device_class == DEVICE_CLASS_HUMIDITY:
                        value = self.get_humidity()

                    entity.push_update(value)
