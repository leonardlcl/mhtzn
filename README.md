# MHTZN

## Installing

> Download and copy `custom_components/mhtzn` folder to `custom_components` folder in your HomeAssistant config folder

> Or you can install component with [HACS](https://hacs.xyz)

## Config

### HomeAssistant GUI

> Configuration > Integration > ➕ > mhtzn
### Configuration variables:

- **host**(*Required*): The IP of your device
- **token**(*Required*): The Token of your device
- **name**(*Optional*): The name of your device
- **model**(*Optional*): The model of your device (like: yeelink.light.ceiling22), Get form miio info if empty
- **mode**(*Optional*): `light,fan` Guess from Model if empty

### Customize entity

```yaml
# configuration.yaml
homeassistant:
  customize: !include customize.yaml
# customize.yaml (Configuration > Customize > Select Entity > Add Other Attribute)
light.your_entity_id:
  support_color: true
  support_brightness: true
  support_color_temp: true
  min_color_temp: 2700
  max_color_temp: 6500
fan.your_entity_id:
  support_oscillate: true
  support_direction: true
```


## Obtain miio token

- Use MiHome mod by [@vevsvevs](https://github.com/custom-components/ble_monitor/issues/7#issuecomment-595874419)
    1. Down apk from [СКАЧАТЬ ВЕРСИЮ 6.x.x](https://www.kapiba.ru/2017/11/mi-home.html)
    2. Create folder `/your_interlal_storage/vevs/logs/`
    3. Find token from `vevs/logs/misc/devices.txt`