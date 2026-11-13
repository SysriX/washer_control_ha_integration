"""binary_sensor.<id>_done – „Wäsche fertig“: an, sobald ein Waschgang fertig ist, aus beim Öffnen der Tür,
beim nächsten Start oder per Quittieren (Dienst washer_control.acknowledge / Karte)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE
from .manager import Washer, WasherManager


async def async_setup_platform(hass: HomeAssistant, _config, async_add_entities: AddEntitiesCallback, _discovery=None) -> None:
    mgr: WasherManager = hass.data[DOMAIN]
    async_add_entities([DoneSensor(w) for w in mgr.washers.values()])


class DoneSensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_icon = "mdi:washing-machine-alert"
    _unrecorded_attributes = frozenset({"minutes_ago"})

    def __init__(self, w: Washer) -> None:
        self.w = w
        self._attr_name = f"{w.name} fertig"
        self._attr_unique_id = f"{DOMAIN}_{w.id}_done"
        self.entity_id = f"binary_sensor.{w.id}_done"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return bool(self.w.d.get("done"))

    @property
    def extra_state_attributes(self) -> dict:
        dn = self.w.done_view()
        return {"program_name": dn["name"], "done_at": dn["at"], "minutes_ago": dn["minutes_ago"]} if dn else {}
