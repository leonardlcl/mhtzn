import asyncio
import logging

from homeassistant.components.zeroconf import ZeroconfServiceInfo, info_from_service
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf, ZeroconfServiceTypes, DNSQuestionType
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser, AsyncServiceInfo

search_map = {}

_LOGGER = logging.getLogger(__name__)


def on_service_state_change(
        zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
) -> None:
    global search_map
    if state_change is ServiceStateChange.Added or state_change is ServiceStateChange.Updated:
        info = zeroconf.get_service_info(service_type, name)
        _LOGGER.warning("state_change : %s ; data : %s", state_change, info)
        discovery_info = info_from_service(info)
        service_type = service_type[:-1]
        name = name.replace(f".{service_type}.", "")
        search_map[name] = discovery_info
    elif state_change is ServiceStateChange.Removed:
        _LOGGER.warning("state_change : %s", state_change)
        service_type = service_type[:-1]
        name = name.replace(f".{service_type}.", "")
        del search_map[name]


async def scan_gateway() -> list:
    global search_map
    zc = Zeroconf(ip_version=IPVersion.All)
    zc.start()
    services = ["_mqtt._tcp.local."]
    kwargs = {'handlers': [on_service_state_change]}
    browser = ServiceBrowser(zc, services, **kwargs)  # type: ignore

    times = 0
    while True:
        if times > 10:
            break
        await asyncio.sleep(1)
        times = times + 1

    search_list = []

    for search in search_map.values():
        search_list.append(search)

    if browser is not None:
        browser.cancel()

    if zc is not None:
        zc.close()

    return search_list
