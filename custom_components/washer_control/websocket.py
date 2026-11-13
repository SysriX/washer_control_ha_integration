"""WebSocket-API für die Waschmaschinen-Karten."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(hass: HomeAssistant) -> None:
    for cmd in (ws_get, ws_programs, ws_start, ws_command, ws_task, ws_settings, ws_ack, ws_history_delete, ws_refresh, ws_debug):
        websocket_api.async_register_command(hass, cmd)


async def _run(connection, msg, fn) -> None:
    try:
        res = fn()
        if hasattr(res, "__await__"):
            res = await res
    except ValueError as err:
        connection.send_error(msg["id"], "washer_error", str(err))
        return
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "washer_error", f"{type(err).__name__}: {err}")
        return
    connection.send_result(msg["id"], res)


def _w(hass, msg):
    return hass.data[DOMAIN].get(msg.get("washer"))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/get", vol.Optional("washer"): str,
                                  vol.Optional("history", default=30): int})
@websocket_api.async_response
async def ws_get(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: _w(hass, msg).snapshot(msg["history"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/programs", vol.Optional("washer"): str})
@websocket_api.async_response
async def ws_programs(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: _w(hass, msg).catalog())


@websocket_api.websocket_command({vol.Required("type"): "washer_control/start", vol.Optional("washer"): str,
                                  vol.Required("program"): str, vol.Optional("parameters", default={}): dict})
@websocket_api.async_response
async def ws_start(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: _w(hass, msg).async_start(msg["program"], msg["parameters"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/command", vol.Optional("washer"): str,
                                  vol.Required("command"): vol.In(["pause", "resume", "stop"])})
@websocket_api.async_response
async def ws_command(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: _w(hass, msg).async_command(msg["command"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/task", vol.Optional("washer"): str,
                                  vol.Required("action"): vol.In(["done", "save", "delete", "reset"]),
                                  vol.Optional("task", default={}): dict})
@websocket_api.async_response
async def ws_task(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: hass.data[DOMAIN].async_task(msg.get("washer"), msg["action"], msg["task"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/settings", vol.Optional("washer"): str,
                                  vol.Required("settings"): dict})
@websocket_api.async_response
async def ws_settings(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: hass.data[DOMAIN].async_settings(msg.get("washer"), msg["settings"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/ack", vol.Optional("washer"): str})
@websocket_api.async_response
async def ws_ack(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: hass.data[DOMAIN].async_ack(msg.get("washer")))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/history_delete", vol.Optional("washer"): str,
                                  vol.Required("history_id"): str})
@websocket_api.async_response
async def ws_history_delete(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: hass.data[DOMAIN].async_history_delete(msg.get("washer"), msg["history_id"]))


@websocket_api.websocket_command({vol.Required("type"): "washer_control/refresh", vol.Optional("washer"): str})
@websocket_api.async_response
async def ws_refresh(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    await _run(connection, msg, lambda: _w(hass, msg).async_refresh())


@websocket_api.websocket_command({vol.Required("type"): "washer_control/debug", vol.Optional("washer"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_debug(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    def fn():
        w = _w(hass, msg)
        a = dict(w.dev.attributes or {}) if w.dev else {}
        par = a.pop("parameters", {})
        return {"parameters": par, "attributes": {k: (v if len(str(v)) < 600 else str(v)[:600]) for k, v in a.items()},
                "statistics": str(getattr(w.dev, "statistics", None))[:800], "cycle": w.d.get("cycle")}
    await _run(connection, msg, fn)
