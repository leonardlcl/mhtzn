"""Support for MQTT JSON lights."""
from contextlib import suppress
import json
import logging

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE_VALUE,
    ATTR_XY_COLOR,
    ENTITY_ID_FORMAT,
    FLASH_LONG,
    FLASH_SHORT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    SUPPORT_EFFECT,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    SUPPORT_WHITE_VALUE,
    VALID_COLOR_MODES,
    ColorMode,
    LightEntity,
    legacy_supported_features,
    valid_supported_color_modes,
)
from homeassistant.const import (
    CONF_BRIGHTNESS,
    CONF_COLOR_TEMP,
    CONF_EFFECT,
    CONF_HS,
    CONF_NAME,
    CONF_OPTIMISTIC,
    CONF_RGB,
    CONF_WHITE_VALUE,
    CONF_XY,
    STATE_ON, CONF_UNIQUE_ID,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.color as color_util

from .. import subscription
from ... import mhtzn
from ..const import (
    CONF_COMMAND_TOPIC,
    CONF_ENCODING,
    CONF_QOS,
    CONF_RETAIN,
    CONF_STATE_TOPIC, LIGHT_MAX_KELVIN, LIGHT_MIN_KELVIN,
)
from ..mixins import MQTT_ENTITY_COMMON_SCHEMA, MqttEntity
from .schema import MQTT_LIGHT_SCHEMA_SCHEMA
from .schema_basic import CONF_BRIGHTNESS_SCALE, MQTT_LIGHT_ATTRIBUTES_BLOCKED

_LOGGER = logging.getLogger(__name__)

DOMAIN = "mqtt_json"

DEFAULT_BRIGHTNESS = False
DEFAULT_COLOR_MODE = False
DEFAULT_COLOR_TEMP = False
DEFAULT_EFFECT = False
DEFAULT_FLASH_TIME_LONG = 10
DEFAULT_FLASH_TIME_SHORT = 2
DEFAULT_NAME = "MQTT JSON Light"
DEFAULT_OPTIMISTIC = False
DEFAULT_RGB = False
DEFAULT_WHITE_VALUE = False
DEFAULT_XY = False
DEFAULT_HS = False
DEFAULT_BRIGHTNESS_SCALE = 255

CONF_COLOR_MODE = "color_mode"
CONF_SUPPORTED_COLOR_MODES = "supported_color_modes"

CONF_EFFECT_LIST = "effect_list"

CONF_FLASH_TIME_LONG = "flash_time_long"
CONF_FLASH_TIME_SHORT = "flash_time_short"

CONF_MAX_MIREDS = "max_mireds"
CONF_MIN_MIREDS = "min_mireds"


def valid_color_configuration(config):
    """Test color_mode is not combined with deprecated config."""
    deprecated = {CONF_COLOR_TEMP, CONF_HS, CONF_RGB, CONF_WHITE_VALUE, CONF_XY}
    if config[CONF_COLOR_MODE] and any(config.get(key) for key in deprecated):
        raise vol.Invalid(f"color_mode must not be combined with any of {deprecated}")
    return config


_PLATFORM_SCHEMA_BASE = (
    mhtzn.MQTT_RW_PLATFORM_SCHEMA.extend(
        {
            vol.Optional(CONF_BRIGHTNESS, default=DEFAULT_BRIGHTNESS): cv.boolean,
            vol.Optional(
                CONF_BRIGHTNESS_SCALE, default=DEFAULT_BRIGHTNESS_SCALE
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Inclusive(
                CONF_COLOR_MODE, "color_mode", default=DEFAULT_COLOR_MODE
            ): cv.boolean,
            vol.Optional(CONF_COLOR_TEMP, default=DEFAULT_COLOR_TEMP): cv.boolean,
            vol.Optional(CONF_EFFECT, default=DEFAULT_EFFECT): cv.boolean,
            vol.Optional(CONF_EFFECT_LIST): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(
                CONF_FLASH_TIME_LONG, default=DEFAULT_FLASH_TIME_LONG
            ): cv.positive_int,
            vol.Optional(
                CONF_FLASH_TIME_SHORT, default=DEFAULT_FLASH_TIME_SHORT
            ): cv.positive_int,
            vol.Optional(CONF_HS, default=DEFAULT_HS): cv.boolean,
            vol.Optional(CONF_MAX_MIREDS): cv.positive_int,
            vol.Optional(CONF_MIN_MIREDS): cv.positive_int,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            vol.Optional(CONF_OPTIMISTIC, default=DEFAULT_OPTIMISTIC): cv.boolean,
            vol.Optional(CONF_QOS, default=mhtzn.DEFAULT_QOS): vol.All(
                vol.Coerce(int), vol.In([0, 1, 2])
            ),
            vol.Optional(CONF_RETAIN, default=mhtzn.DEFAULT_RETAIN): cv.boolean,
            vol.Optional(CONF_RGB, default=DEFAULT_RGB): cv.boolean,
            vol.Optional(CONF_STATE_TOPIC): mhtzn.valid_subscribe_topic,
            vol.Inclusive(CONF_SUPPORTED_COLOR_MODES, "color_mode"): vol.All(
                cv.ensure_list,
                [vol.In(VALID_COLOR_MODES)],
                vol.Unique(),
                valid_supported_color_modes,
            ),
            vol.Optional(CONF_WHITE_VALUE, default=DEFAULT_WHITE_VALUE): cv.boolean,
            vol.Optional(CONF_XY, default=DEFAULT_XY): cv.boolean,
        },
    )
    .extend(MQTT_ENTITY_COMMON_SCHEMA.schema)
    .extend(MQTT_LIGHT_SCHEMA_SCHEMA.schema)
)

PLATFORM_SCHEMA_JSON = vol.All(
    _PLATFORM_SCHEMA_BASE,
    valid_color_configuration,
)

DISCOVERY_SCHEMA_JSON = vol.All(
    _PLATFORM_SCHEMA_BASE.extend({}, extra=vol.REMOVE_EXTRA),
    valid_color_configuration,
)


async def async_setup_entity_json(
        hass, config: ConfigType, async_add_entities, config_entry, discovery_data
):
    """Set up a MQTT JSON Light."""
    async_add_entities([MqttLightJson(hass, config, config_entry, discovery_data)])


class MqttLightJson(MqttEntity, LightEntity, RestoreEntity):
    """Representation of a MQTT JSON light."""

    _entity_id_format = ENTITY_ID_FORMAT
    _attributes_extra_blocked = MQTT_LIGHT_ATTRIBUTES_BLOCKED

    def __init__(self, hass, config, config_entry, discovery_data):
        """Initialize MQTT JSON light."""
        self._state = None
        self._supported_features = 0

        self._topic = None
        self._optimistic = False
        self._brightness = None
        self._color_mode = None
        self._color_temp = None
        self._effect = None
        self._flash_times = None
        self._hs = None
        self._rgb = None
        self._rgbw = None
        self._rgbww = None
        self._white_value = None
        self._xy = None

        MqttEntity.__init__(self, hass, config, config_entry, discovery_data)

    @staticmethod
    def config_schema():
        """Return the config schema."""
        return DISCOVERY_SCHEMA_JSON

    def _setup_from_config(self, config):
        """(Re)Setup the entity."""
        self._topic = {
            key: config.get(key) for key in (CONF_STATE_TOPIC, CONF_COMMAND_TOPIC)
        }
        optimistic = config[CONF_OPTIMISTIC]
        self._optimistic = optimistic or self._topic[CONF_STATE_TOPIC] is None

        self._flash_times = {
            key: config.get(key)
            for key in (CONF_FLASH_TIME_SHORT, CONF_FLASH_TIME_LONG)
        }

        self._supported_features = SUPPORT_TRANSITION | SUPPORT_FLASH
        self._supported_features |= config[CONF_EFFECT] and SUPPORT_EFFECT
        if not self._config[CONF_COLOR_MODE]:
            self._supported_features |= config[CONF_BRIGHTNESS] and SUPPORT_BRIGHTNESS
            self._supported_features |= config[CONF_COLOR_TEMP] and SUPPORT_COLOR_TEMP
            self._supported_features |= config[CONF_HS] and SUPPORT_COLOR
            self._supported_features |= config[CONF_RGB] and (
                    SUPPORT_COLOR | SUPPORT_BRIGHTNESS
            )
            self._supported_features |= config[CONF_WHITE_VALUE] and SUPPORT_WHITE_VALUE
            self._supported_features |= config[CONF_XY] and SUPPORT_COLOR

    def _update_color(self, values):
        if not self._config[CONF_COLOR_MODE]:
            # Deprecated color handling
            try:
                red = int(values["color"]["r"])
                green = int(values["color"]["g"])
                blue = int(values["color"]["b"])
                self._hs = color_util.color_RGB_to_hs(red, green, blue)
            except KeyError:
                pass
            except ValueError:
                _LOGGER.warning("Invalid RGB color value received")
                return

            try:
                x_color = float(values["color"]["x"])
                y_color = float(values["color"]["y"])
                self._hs = color_util.color_xy_to_hs(x_color, y_color)
            except KeyError:
                pass
            except ValueError:
                _LOGGER.warning("Invalid XY color value received")
                return

            try:
                hue = float(values["color"]["h"])
                saturation = float(values["color"]["s"])
                self._hs = (hue, saturation)
            except KeyError:
                pass
            except ValueError:
                _LOGGER.warning("Invalid HS color value received")
                return
        else:
            color_mode = values["color_mode"]
            if not self._supports_color_mode(color_mode):
                _LOGGER.warning("Invalid color mode received")
                return
            try:
                if color_mode == ColorMode.COLOR_TEMP:
                    self._color_temp = int(values["color_temp"])
                    self._color_mode = ColorMode.COLOR_TEMP
                elif color_mode == ColorMode.HS:
                    hue = float(values["color"]["h"])
                    saturation = float(values["color"]["s"])
                    self._color_mode = ColorMode.HS
                    self._hs = (hue, saturation)
                elif color_mode == ColorMode.RGB:
                    r = int(values["color"]["r"])  # pylint: disable=invalid-name
                    g = int(values["color"]["g"])  # pylint: disable=invalid-name
                    b = int(values["color"]["b"])  # pylint: disable=invalid-name
                    self._color_mode = ColorMode.RGB
                    self._rgb = (r, g, b)
                elif color_mode == ColorMode.RGBW:
                    r = int(values["color"]["r"])  # pylint: disable=invalid-name
                    g = int(values["color"]["g"])  # pylint: disable=invalid-name
                    b = int(values["color"]["b"])  # pylint: disable=invalid-name
                    w = int(values["color"]["w"])  # pylint: disable=invalid-name
                    self._color_mode = ColorMode.RGBW
                    self._rgbw = (r, g, b, w)
                elif color_mode == ColorMode.RGBWW:
                    r = int(values["color"]["r"])  # pylint: disable=invalid-name
                    g = int(values["color"]["g"])  # pylint: disable=invalid-name
                    b = int(values["color"]["b"])  # pylint: disable=invalid-name
                    c = int(values["color"]["c"])  # pylint: disable=invalid-name
                    w = int(values["color"]["w"])  # pylint: disable=invalid-name
                    self._color_mode = ColorMode.RGBWW
                    self._rgbww = (r, g, b, c, w)
                elif color_mode == ColorMode.XY:
                    x = float(values["color"]["x"])  # pylint: disable=invalid-name
                    y = float(values["color"]["y"])  # pylint: disable=invalid-name
                    self._color_mode = ColorMode.XY
                    self._xy = (x, y)
            except (KeyError, ValueError):
                _LOGGER.warning("Invalid or incomplete color value received")

    def _prepare_subscribe_topics(self):
        """(Re)Subscribe to topics."""

        @callback
        def state_received(msg):
            """Handle new MQTT messages."""
            payload = json.loads(msg.payload)

            data = payload["data"]

            sn = self._config[CONF_UNIQUE_ID]

            values = None

            for state in data:
                if state["sn"] == sn:
                    values = state

            if values is None:
                return

            if "on" in values:
                if values["on"] == 1:
                    self._state = True
                elif values["on"] == 0:
                    self._state = False
                elif values["on"] is None:
                    self._state = None

            if "rgb" in values:
                rgb = values["rgb"]
                blue = rgb & 255
                green = (rgb >> 8) & 255
                red = (rgb >> 16) & 255
                self._rgb = (red, green, blue)

            if "level" in values:
                try:
                    self._brightness = int(
                        values["level"] * 255
                    )
                except KeyError:
                    pass
                except (TypeError, ValueError):
                    _LOGGER.warning("Invalid brightness value received")

            if "kelvin" in values:
                try:
                    kelvin = int(values["kelvin"])
                    if kelvin > LIGHT_MAX_KELVIN:
                        kelvin = LIGHT_MAX_KELVIN
                    if kelvin < LIGHT_MIN_KELVIN:
                        kelvin = LIGHT_MIN_KELVIN
                    kelvin = (kelvin - LIGHT_MIN_KELVIN) / (LIGHT_MAX_KELVIN - LIGHT_MIN_KELVIN)
                    kelvin = round(153 + kelvin * (500 - 153))
                    kelvin = 500 - kelvin + 153
                    self._color_temp = kelvin
                except KeyError:
                    pass
                except ValueError:
                    _LOGGER.warning("Invalid color temp value received")

            self.async_write_ha_state()

        if self._topic[CONF_STATE_TOPIC] is not None:
            self._sub_state = subscription.async_prepare_subscribe_topics(
                self.hass,
                self._sub_state,
                {
                    "state_topic": {
                        "topic": self._topic[CONF_STATE_TOPIC],
                        "msg_callback": state_received,
                        "qos": self._config[CONF_QOS],
                        "encoding": self._config[CONF_ENCODING] or None,
                    }
                },
            )

    async def _subscribe_topics(self):
        """(Re)Subscribe to topics."""
        await subscription.async_subscribe_topics(self.hass, self._sub_state)

        last_state = await self.async_get_last_state()
        if self._optimistic and last_state:
            self._state = last_state.state == STATE_ON
            last_attributes = last_state.attributes
            self._brightness = last_attributes.get(ATTR_BRIGHTNESS, self._brightness)
            self._color_mode = last_attributes.get(ATTR_COLOR_MODE, self._color_mode)
            self._color_temp = last_attributes.get(ATTR_COLOR_TEMP, self._color_temp)
            self._effect = last_attributes.get(ATTR_EFFECT, self._effect)
            self._hs = last_attributes.get(ATTR_HS_COLOR, self._hs)
            self._rgb = last_attributes.get(ATTR_RGB_COLOR, self._rgb)
            self._rgbw = last_attributes.get(ATTR_RGBW_COLOR, self._rgbw)
            self._rgbww = last_attributes.get(ATTR_RGBWW_COLOR, self._rgbww)
            self._white_value = last_attributes.get(ATTR_WHITE_VALUE, self._white_value)
            self._xy = last_attributes.get(ATTR_XY_COLOR, self._xy)

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def color_temp(self):
        """Return the color temperature in mired."""
        return self._color_temp

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        return self._config.get(CONF_MIN_MIREDS, super().min_mireds)

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        return self._config.get(CONF_MAX_MIREDS, super().max_mireds)

    @property
    def effect(self):
        """Return the current effect."""
        return self._effect

    @property
    def effect_list(self):
        """Return the list of supported effects."""
        return self._config.get(CONF_EFFECT_LIST)

    @property
    def hs_color(self):
        """Return the hs color value."""
        return self._hs

    @property
    def rgb_color(self):
        """Return the hs color value."""
        return self._rgb

    @property
    def rgbw_color(self):
        """Return the hs color value."""
        return self._rgbw

    @property
    def rgbww_color(self):
        """Return the hs color value."""
        return self._rgbww

    @property
    def xy_color(self):
        """Return the hs color value."""
        return self._xy

    @property
    def white_value(self):
        """Return the white property."""
        return self._white_value

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    @property
    def assumed_state(self):
        """Return true if we do optimistic updates."""
        return self._optimistic

    @property
    def color_mode(self):
        """Return current color mode."""
        return self._color_mode

    @property
    def supported_color_modes(self):
        """Flag supported color modes."""
        return self._config.get(CONF_SUPPORTED_COLOR_MODES)

    @property
    def supported_features(self):
        """Flag supported features."""
        return legacy_supported_features(
            self._supported_features, self._config.get(CONF_SUPPORTED_COLOR_MODES)
        )

    def _set_flash_and_transition(self, message, **kwargs):
        if ATTR_TRANSITION in kwargs:
            message["transition"] = kwargs[ATTR_TRANSITION]

        if ATTR_FLASH in kwargs:
            flash = kwargs.get(ATTR_FLASH)

            if flash == FLASH_LONG:
                message["flash"] = self._flash_times[CONF_FLASH_TIME_LONG]
            elif flash == FLASH_SHORT:
                message["flash"] = self._flash_times[CONF_FLASH_TIME_SHORT]

    def _scale_rgbxx(self, rgbxx, kwargs):
        # If there's a brightness topic set, we don't want to scale the
        # RGBxx values given using the brightness.
        if self._config[CONF_BRIGHTNESS]:
            brightness = 255
        else:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        return tuple(round(i / 255 * brightness) for i in rgbxx)

    def _supports_color_mode(self, color_mode):
        return self.supported_color_modes and color_mode in self.supported_color_modes

    async def async_turn_on(self, **kwargs):  # noqa: C901
        """Turn the device on.

        This method is a coroutine.
        """
        should_update = False

        sn = self._config[CONF_UNIQUE_ID]

        message = {
            "seq": 1,
            "data": {
                "sn": sn,
                "on": 1
            }
        }

        if ATTR_RGB_COLOR in kwargs and self._supports_color_mode(ColorMode.RGB):
            rgb = self._scale_rgbxx(kwargs[ATTR_RGB_COLOR], kwargs)
            message["data"]["rgb"] = (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]
            if message["data"].get("on") is not None:
                del message["data"]["on"]
            if self._optimistic:
                self._color_mode = ColorMode.RGB
                self._rgb = rgb
                should_update = True

        if ATTR_BRIGHTNESS in kwargs and self._config[CONF_BRIGHTNESS]:
            brightness_normalized = kwargs[ATTR_BRIGHTNESS] / DEFAULT_BRIGHTNESS_SCALE
            device_brightness = round(brightness_normalized, 4)
            message["data"]["level"] = device_brightness
            if message["data"].get("on") is not None:
                del message["data"]["on"]

            if self._optimistic:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                should_update = True

        if ATTR_COLOR_TEMP in kwargs:
            kelvin = int(kwargs[ATTR_COLOR_TEMP])

            kelvin = (kelvin - 153) / (500 - 153)

            kelvin = round(LIGHT_MIN_KELVIN + kelvin * (LIGHT_MAX_KELVIN - LIGHT_MIN_KELVIN))

            kelvin = LIGHT_MAX_KELVIN - kelvin + LIGHT_MIN_KELVIN

            if kelvin > LIGHT_MAX_KELVIN:
                kelvin = LIGHT_MAX_KELVIN

            if kelvin < LIGHT_MIN_KELVIN:
                kelvin = LIGHT_MIN_KELVIN

            message["data"]["kelvin"] = kelvin
            if message["data"].get("on") is not None:
                del message["data"]["on"]

            if self._optimistic:
                self._color_temp = kwargs[ATTR_COLOR_TEMP]
                should_update = True

        await self.async_publish(
            self._topic[CONF_COMMAND_TOPIC],
            json.dumps(message),
            self._config[CONF_QOS],
            self._config[CONF_RETAIN],
            self._config[CONF_ENCODING],
        )

        if self._optimistic:
            # Optimistically assume that the light has changed state.
            self._state = True
            should_update = True

        if should_update:
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the device off.

        This method is a coroutine.
        """
        sn = self._config[CONF_UNIQUE_ID]

        message = {
            "seq": 1,
            "data": {
                "sn": sn,
                "on": 0
            }
        }

        self._set_flash_and_transition(message, **kwargs)

        await self.async_publish(
            self._topic[CONF_COMMAND_TOPIC],
            json.dumps(message),
            self._config[CONF_QOS],
            self._config[CONF_RETAIN],
            self._config[CONF_ENCODING],
        )

        if self._optimistic:
            # Optimistically assume that the light has changed state.
            self._state = False
            self.async_write_ha_state()
