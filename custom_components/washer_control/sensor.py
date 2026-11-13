"""sensor.<id>_status (bereit/laeuft/pausiert/geplant/fertig/fehler …, Attribute = aktueller Waschgang)
und sensor.<id>_maintenance (Anzahl fälliger Wartungsaufgaben)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE, VERSION
from .manager import Washer, WasherManager

STATE_NAMES = {"bereit": "Bereit", "laeuft": "Läuft", "pausiert": "Pausiert", "geplant": "Geplant", "fertig": "Wäsche fertig",
               "fehler": "Fehler", "beendet": "Beendet", "getrennt": "Getrennt", "aus": "Aus", "test": "Test"}


async def async_setup_platform(hass: HomeAssistant, _config, async_add_entities: AddEntitiesCallback, _discovery=None) -> None:
    mgr: WasherManager = hass.data[DOMAIN]
    ents = []
    for w in mgr.washers.values():
        ents += [StatusSensor(w), MaintenanceSensor(w)]
    async_add_entities(ents)


class _Base(SensorEntity):
    _attr_should_poll = False

    def __init__(self, w: Washer) -> None:
        self.w = w

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.w.dev is not None


class StatusSensor(_Base):
    _attr_icon = "mdi:washing-machine"
    _unrecorded_attributes = frozenset({"progress", "remaining", "water", "energy", "phases", "version", "door_locked", "detergent", "power"})

    def __init__(self, w: Washer) -> None:
        super().__init__(w)
        self._attr_name = f"{w.name} Status"
        self._attr_unique_id = f"{DOMAIN}_{w.id}_status"
        self.entity_id = f"sensor.{w.id}_status"

    @property
    def native_value(self) -> str:
        return self.w.state()

    @property
    def extra_state_attributes(self) -> dict:
        w, L = self.w, self.w.live
        c = w.cycle_view() or {}
        dn = w.done_view()
        st = w.state()
        return {
            "washer": w.id, "state_name": STATE_NAMES.get(st, st), "program": c.get("program") or L.get("program"),
            "program_name": c.get("name") or L.get("program_name"), "phase": L.get("phase_name"), "phase_kind": L.get("phase_kind"),
            "start": c.get("start"), "planned_start": c.get("planned_start"), "end": c.get("end"), "remaining": L.get("remaining"),
            "progress": round(c["progress"] * 100) if c.get("progress") is not None else None,
            "temp": c.get("temp") if c else L.get("temp"), "spin": c.get("spin") if c else L.get("spin"),
            "water": L.get("water"), "energy": L.get("energy"), "phases": c.get("phases"),
            "done_at": dn["at"] if dn else None, "done_program": dn["name"] if dn else None,
            "door_open": L.get("door_open"), "door_locked": L.get("door_locked"), "remote": L.get("remote"),
            "error": L.get("error") if L.get("error") not in (None, "", "00", "0") else None, "detergent": L.get("detergent"), "detergent_warn": L.get("detergent_warn"), "softener_warn": L.get("softener_warn"),
            "maintenance_due": sum(1 for t in w.tasks_view() if t["due"]), "power": L.get("power"),
            "anti_crease": L.get("anti_crease_active"), "plug_on": L.get("plug_on"), "version": VERSION,
        }


class MaintenanceSensor(_Base):
    _attr_icon = "mdi:wrench-clock"
    _attr_native_unit_of_measurement = None
    _unrecorded_attributes = frozenset({"tasks"})

    def __init__(self, w: Washer) -> None:
        super().__init__(w)
        self._attr_name = f"{w.name} Wartung fällig"
        self._attr_unique_id = f"{DOMAIN}_{w.id}_maintenance"
        self.entity_id = f"sensor.{w.id}_maintenance"

    @property
    def native_value(self) -> int:
        return sum(1 for t in self.w.tasks_view() if t["due"])

    @property
    def extra_state_attributes(self) -> dict:
        T = self.w.tasks_view()
        return {"faellig": [t["name"] for t in T if t["due"]], "bald": [t["name"] for t in T if t["soon"]],
                "tasks": [{k: t.get(k) for k in ("id", "name", "ratio", "days_since", "washes_since", "due")} for t in T]}
