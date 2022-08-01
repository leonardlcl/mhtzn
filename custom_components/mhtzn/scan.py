import asyncio
import logging

from homeassistant.components import zeroconf
from homeassistant.components.zeroconf import ZeroconfServiceInfo, info_from_service
from homeassistant.core import HomeAssistant
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf, ZeroconfServiceTypes

search_map = {}

flag = False

_LOGGER = logging.getLogger(__name__)


def on_service_state_change(
        **kwargs
) -> None:
    if kwargs["state_change"] is ServiceStateChange.Added or kwargs["state_change"] is ServiceStateChange.Updated:
        service_type = kwargs["service_type"]
        name = kwargs["name"]
        info = kwargs["zeroconf"].get_service_info(service_type, name)
        discovery_info = info_from_service(info)
        service_type = service_type[:-1]
        name = name.replace(f".{service_type}.", "")
        search_map[name] = discovery_info
    elif kwargs["state_change"] is ServiceStateChange.Removed:
        service_type = kwargs["service_type"]
        name = kwargs["name"]
        service_type = service_type[:-1]
        name = name.replace(f".{service_type}.", "")
        del search_map[name]


async def scan_gateway(hass: HomeAssistant) -> list:
    global flag

    if not flag:
        zc = await zeroconf.async_get_instance(hass)
        services = ["_mqtt._tcp.local."]
        ServiceBrowser(zc, services, handlers=[on_service_state_change])
        flag = True

    times = 0
    while True:
        if times > 1:
            break
        await asyncio.sleep(1)
        times = times + 1

    search_list = []

    for search in search_map.values():
        search_list.append(search)

    return search_list
