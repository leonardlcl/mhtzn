"""Config flow for Hello World integration."""
from __future__ import annotations

import logging
import queue
from collections import OrderedDict

import voluptuous as vol
from typing import Any

from homeassistant import config_entries, exceptions
from homeassistant.components import zeroconf
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import (
    CONF_DISCOVERY,
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_USERNAME,
)

from .client import MqttClientSetup
from .scan import scan_gateway
from .const import (
    DATA_MQTT_CONFIG,
    CONF_BROKER,
    DEFAULT_DISCOVERY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# This is the schema that used to display the UI to the user. This simple
# schema has a single required host field, but it could include a number of fields
# such as username, password etc. See other components in the HA core code for
# further examples.
# Note the input displayed to the user will be translated. See the
# translations/<lang>.json file and strings.json. See here for further information:
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler/#translations
# At the time of writing I found the translations created by the scaffold didn't
# quite work as documented and always gave me the "Lokalise key references" string
# (in square brackets), rather than the actual translated value. I did not attempt to
# figure this out or look further into it.
DATA_SCHEMA = vol.Schema({("host"): str})

connection_store_dict = {}

MQTT_TIMEOUT = 5

CONF_OPT_TYPE = "opt_type"


def _get_name(discovery_info):
    service_type = discovery_info.type[:-1]  # Remove leading .
    return discovery_info.name.replace(f".{service_type}.", "")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hello World."""

    VERSION = 1
    # Pick one of the available connection classes in homeassistant/config_entries.py
    # This tells HA if it should be asking for updates, or it'll be notified of updates
    # automatically. This example uses PUSH, as the dummy hub will notify HA of
    # changes.
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_zeroconf(
            self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""

        connection_dict = self._get_connection_dict(discovery_info)

        for entry in self._async_current_entries():
            entry_data = entry.data
            if entry_data[CONF_NAME] == connection_dict[CONF_NAME]:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=connection_dict,
                )

        return self.async_abort(reason="not_xiaomi_miio")

    def _get_connection_dict(self, discovery_info):
        name = _get_name(discovery_info)
        host = discovery_info.host
        port = discovery_info.port
        username = None
        password = None

        if name in self.hass.data:
            default_info = self.hass.data[name]
            if "username" in default_info:
                username = default_info["username"]
            if "password" in default_info:
                password = default_info["password"]
        else:
            self.hass.data[name] = {}

        for key, value in discovery_info.properties.items():
            if key == 'username':
                username = value
                self.hass.data[name]["username"] = username
            elif key == 'password':
                password = value
                self.hass.data[name]["password"] = password
            elif key == 'host':
                host = value

        return {
            CONF_NAME: name,
            CONF_BROKER: host,
            CONF_PORT: port,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
        }

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_option()

    async def async_step_option(self, user_input=None):
        """Confirm the setup."""
        errors = {}

        if user_input is not None:
            opt_type = user_input[CONF_OPT_TYPE]
            if opt_type == "??????":
                return await self.async_step_scan()
            elif opt_type == "??????":
                return await self.async_step_custom()

        fields = OrderedDict()
        fields[vol.Required(CONF_OPT_TYPE)] = vol.In(["??????", "??????"])

        return self.async_show_form(
            step_id="option", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_scan(self, user_input=None):
        """Confirm the setup."""
        errors = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            connection_dict = connection_store_dict.get(name)
            if connection_dict is not None:
                can_connect = await self.hass.async_add_executor_job(
                    try_connection,
                    self.hass,
                    connection_dict[CONF_BROKER],
                    connection_dict[CONF_PORT],
                    connection_dict[CONF_USERNAME],
                    connection_dict[CONF_PASSWORD],
                )
                if can_connect:
                    connection_dict[CONF_DISCOVERY] = DEFAULT_DISCOVERY
                    return self.async_create_entry(
                        title=connection_dict[CONF_NAME], data=connection_dict
                    )
                else:
                    errors["base"] = "cannot_connect"
            else:
                return self.async_abort(reason="select_error")

        discovery_list = await scan_gateway()

        connection_store_dict.clear()
        for info in discovery_list:
            name = _get_name(info)
            connection_dict = self._get_connection_dict(info)
            connection_store_dict[name] = connection_dict

        selectable_list = []

        for key in list(connection_store_dict.keys()):
            selectable_list.append(key)

        if len(selectable_list) < 1:
            return self.async_abort(reason="not_found_device")

        fields = OrderedDict()
        fields[vol.Required(CONF_NAME)] = vol.In(selectable_list)

        return self.async_show_form(
            step_id="scan", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_custom(self, user_input=None):
        """Confirm the setup."""
        errors = {}

        if user_input is not None:
            connection_dict = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_BROKER: user_input[CONF_BROKER],
                CONF_PORT: user_input[CONF_PORT],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            if connection_dict is not None:
                can_connect = await self.hass.async_add_executor_job(
                    try_connection,
                    self.hass,
                    connection_dict[CONF_BROKER],
                    connection_dict[CONF_PORT],
                    connection_dict[CONF_USERNAME],
                    connection_dict[CONF_PASSWORD],
                )
                if can_connect:
                    connection_dict[CONF_DISCOVERY] = DEFAULT_DISCOVERY
                    return self.async_create_entry(
                        title=connection_dict[CONF_NAME], data=connection_dict
                    )
                else:
                    errors["base"] = "cannot_connect"
            else:
                return self.async_abort(reason="select_error")

        fields = OrderedDict()
        fields[vol.Required(CONF_NAME, default="IG1-01")] = str
        fields[vol.Required(CONF_BROKER)] = str
        fields[vol.Required(CONF_PORT, default=1883)] = vol.Coerce(int)
        fields[vol.Required(CONF_USERNAME)] = str
        fields[vol.Required(CONF_PASSWORD)] = str

        return self.async_show_form(
            step_id="custom", data_schema=vol.Schema(fields), errors=errors
        )


def try_connection(hass, broker, port, username, password, protocol="3.1.1"):
    """Test if we can connect to an MQTT broker."""
    # We don't import on the top because some integrations
    # should be able to optionally rely on MQTT.
    import paho.mqtt.client as mqtt  # pylint: disable=import-outside-toplevel

    # Get the config from configuration.yaml
    yaml_config = hass.data.get(DATA_MQTT_CONFIG, {})
    entry_config = {
        CONF_BROKER: broker,
        CONF_PORT: port,
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_PROTOCOL: protocol,
    }
    client = MqttClientSetup({**yaml_config, **entry_config}).client

    result = queue.Queue(maxsize=1)

    def on_connect(client_, userdata, flags, result_code):
        """Handle connection result."""
        result.put(result_code == mqtt.CONNACK_ACCEPTED)

    client.on_connect = on_connect

    client.connect_async(broker, port)
    client.loop_start()

    try:
        return result.get(timeout=MQTT_TIMEOUT)
    except queue.Empty:
        return False
    finally:
        client.disconnect()
        client.loop_stop()


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
