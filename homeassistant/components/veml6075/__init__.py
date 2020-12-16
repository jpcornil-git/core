"""Support for I2C VEML6075 UV sensor."""
import logging
import threading

from homeassistant.components.sensor import DEVICE_CLASS_UV

from .const import DEVICE_CLASS_UV_INTENSITY

# VEML6075 Register Map
R_UV_CONF = 0x00
R_UVA_Data = 0x07
R_UVB_Data = 0x09
R_UVCOMP1_Data = 0x0A
R_UVCOMP2_Data = 0x0B
R_ID = 0x0C

# VEML6075 diffusor default Coefficients (from "Designing the VEML6075 into an appalication" Application Note)
C_UVA_VISIBLE = 2.22
C_UVA_IR = 1.33
C_UVA_RESPONSIVITY = 0.001491  # 100ms integration time
C_UVB_VISIBLE = 2.95
C_UVB_IR = 1.74
C_UVB_RESPONSIVITY = 0.002591  # 100ms integration time

_LOGGER = logging.getLogger(__name__)


class VEML6075:
    """VEML6075 device driver."""

    def __init__(self, bus, address, slowdown):
        """Create a VEML6075 instance at {address} on I2C {bus} with default coefficients."""
        self._bus = bus
        self._address = address
        self._slowdown = slowdown
        self._slowdown_counter = 0

        self._device_lock = threading.Lock()
        self._entities = dict()

        device_id = self[R_ID]
        if device_id != 0x0026:
            # FIXME: Should we bail out somehow here ... ?
            _LOGGER.warning(
                "%s @ 0x%02x, bad device identification (0x%04x)",
                type(self).__name__,
                address,
                device_id,
            )

        # Power up [0] and set 800ms integration time [6:4]
        self[R_UV_CONF] = 0x4 << 4
        self.coef_integration = 8

        self.coef_uva_visible = float(C_UVA_VISIBLE)
        self.coef_uva_ir = float(C_UVA_IR)
        self.coef_uva_responsivity = float(C_UVA_RESPONSIVITY)
        self.coef_uvb_visible = float(C_UVB_VISIBLE)
        self.coef_uvb_ir = float(C_UVB_IR)
        self.coef_uvb_responsivity = float(C_UVB_RESPONSIVITY)

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
        """Set VEML6075 {register} to {value}."""
        self._bus.write_word_data(self._address, register, value)

    def __getitem__(self, register):
        """Get value of VEML6075 {register}."""
        data = self._bus.read_word_data(self._address, register)
        return data

    @property
    def address(self):
        """Return device address."""
        return self._address

    def set_uv_coefficients(
        self,
        coef_uva_visible,
        coef_uva_ir,
        coef_uva_responsivity,
        coef_uvb_visible,
        coef_uvb_ir,
        coef_uvb_responsivity,
    ):
        """Set VEML6075 light coefficients from sensor calibration."""
        self.coef_uva_visible = float(coef_uva_visible)
        self.coef_uva_ir = float(coef_uva_ir)
        self.coef_uva_responsivity = float(coef_uva_responsivity)
        self.coef_uvb_visible = float(coef_uvb_visible)
        self.coef_uvb_ir = float(coef_uvb_ir)
        self.coef_uvb_responsivity = float(coef_uvb_responsivity)

    def str_uv_intensity(self, index):
        """Return UV intensity as a string."""
        if index < 2:
            return "Low"
        elif index < 5:
            return "Moderate"
        elif index < 7:
            return "High"
        elif index < 10:
            return "Very high"
        elif index < 12:
            return "Extreme"

        return "Error"

    def get_uv_index(self):
        """Return UV index.

        Access should be protected by a with statement to avoid threading issues.
        """
        # Read COMP values
        uv_comp_visible = float(self[R_UVCOMP1_Data])
        uv_comp_ir = float(self[R_UVCOMP2_Data])

        # Read UVA and UVB values and compute UV index
        uva_raw = float(self[R_UVA_Data])
        uvb_raw = float(self[R_UVB_Data])

        uva_digital = (
            uva_raw
            - self.coef_uva_visible * uv_comp_visible
            - self.coef_uva_ir * uv_comp_ir
        )
        uva = max(0, (uva_digital * self.coef_uva_responsivity) / self.coef_integration)

        uvb_digital = (
            uvb_raw
            - self.coef_uvb_visible * uv_comp_visible
            - self.coef_uvb_ir * uv_comp_ir
        )
        uvb = max(0, (uvb_digital * self.coef_uvb_responsivity) / self.coef_integration)

        return (uva + uvb) / 2.0

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
                    if device_class == DEVICE_CLASS_UV:
                        value = self.get_uv_index()
                    elif device_class == DEVICE_CLASS_UV_INTENSITY:
                        value = self.str_uv_intensity()

                    entity.push_update(value)
