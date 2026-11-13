"""Waschmaschinen-Steuerung (washer_control) – hOn-Waschmaschine bedienen, Waschgänge erkennen,
„Wäsche fertig“ melden, Verlauf/Statistik/Wartung in .storage/washer_control.

configuration.yaml:

    washer_control:
      devices:
        - id: ku_washer          # → sensor.ku_washer_status, binary_sensor.ku_washer_done, sensor.ku_washer_maintenance
          name: Waschmaschine
          room: ku
          # hon_device: <device_id>   optional, sonst erste hOn-Waschmaschine
          plug:                       # optional: Zwischenstecker mit Messung (Leistungskurve, kWh je Waschgang)
            power: sensor.washer_plug_power
            energy: sensor.washer_plug_energy_total
            switch: switch.washer_plug

Ereignisse: washer_control_started, washer_control_finished (result fertig|abgebrochen, program, name, minutes, water, energy)
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .const import DOMAIN
from .manager import WasherManager

DEFAULT_DEVICES = [{"id": "ku_washer", "name": "Waschmaschine", "room": "ku"}]
DEV_SCHEMA = vol.Schema({
    vol.Required("id"): cv.slug,
    vol.Optional("name", default="Waschmaschine"): cv.string,
    vol.Optional("room"): cv.slug,
    vol.Optional("hon_device"): cv.string,
    vol.Optional("plug"): vol.Schema({vol.Optional("power"): cv.entity_id, vol.Optional("energy"): cv.entity_id,
                                       vol.Optional("switch"): cv.entity_id}),
})
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Any(None, vol.Schema({
    vol.Optional("devices", default=DEFAULT_DEVICES): vol.All(cv.ensure_list, [DEV_SCHEMA]),
}))}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    conf = config.get(DOMAIN) or {}
    mgr = WasherManager(hass, conf.get("devices") or DEFAULT_DEVICES)
    hass.data[DOMAIN] = mgr
    websocket.async_register(hass)
    await mgr.async_start()

    async def _stop(_ev) -> None:
        await mgr.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

    async def _guard(coro):
        try:
            return await coro
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def start(call: ServiceCall) -> None:
        await _guard(mgr.get(call.data.get("washer")).async_start(call.data["program"], call.data.get("parameters") or {}))

    async def command(call: ServiceCall) -> None:
        await _guard(mgr.get(call.data.get("washer")).async_command(call.data["command"]))

    async def ack(call: ServiceCall) -> None:
        await _guard(mgr.async_ack(call.data.get("washer")))

    async def task_done(call: ServiceCall) -> None:
        await _guard(mgr.async_task(call.data.get("washer"), "done", {"id": call.data["task"]}))

    hass.services.async_register(DOMAIN, "start", start, vol.Schema({
        vol.Optional("washer"): cv.string, vol.Required("program"): cv.string, vol.Optional("parameters"): dict}))
    hass.services.async_register(DOMAIN, "command", command, vol.Schema({
        vol.Optional("washer"): cv.string, vol.Required("command"): vol.In(["pause", "resume", "stop"])}))
    hass.services.async_register(DOMAIN, "acknowledge", ack, vol.Schema({vol.Optional("washer"): cv.string}))
    hass.services.async_register(DOMAIN, "task_done", task_done, vol.Schema({
        vol.Optional("washer"): cv.string, vol.Required("task"): cv.string}))

    for platform in ("sensor", "binary_sensor"):
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    return True
