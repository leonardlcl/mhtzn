[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
# MHTZN

## Installing

> Download and copy `custom_components/mhtzn` folder to `custom_components` folder in your HomeAssistant config folder

> Or you can install component with [HACS](https://hacs.xyz)

## Config

### HomeAssistant GUI

> Configuration > Integration > ➕ > mhtzn
### Configuration variables:
#### scan
> Scan the LAN's list of gateway device information and select one to connect
#### custom

- **Gateway ID**(*Required*): The identification of your gateway
- **Gateway IP**(*Required*): The IP address of your gateway
- **Port**(*Required*): The MQTT port number of your gateway
- **Username**(*Required*): The MQTT username of your gateway
- **Password**(*Required*): The MQTT password of your gateway
