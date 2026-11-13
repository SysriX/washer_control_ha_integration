"""Waschmaschinen-Steuerung: liest die hOn-Waschmaschine direkt aus der hOn-Integration (Koordinator),
erkennt Waschgänge (Start/Ende), merkt sich Verlauf, Statistik und Wartung und startet/steuert Programme."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (DEFAULT_TASKS, END_MODES, EVENT_FINISHED, EVENT_STARTED, GROUPS, HISTORY_MAX, HON, MODES, PHASE_KIND,
                    PHASES, PLAN_MODES, PROGRAMS, RUN_MODES, SIGNAL_UPDATE, STORE_KEY, STORE_VERSION, VERSION)

_LOGGER = logging.getLogger(__name__)


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def _num(v: Any, d: float | None = None) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return d


def _int(v: Any, d: int | None = None) -> int | None:
    n = _num(v)
    return int(n) if n is not None else d


def prog_label(key: str | None) -> str:
    if not key:
        return ""
    if key in PROGRAMS:
        return PROGRAMS[key][0]
    k = key.replace("iot_wash_", "").replace("hqd_", "").replace("_", " ")
    return k[:1].upper() + k[1:]


class Washer:
    """Eine Waschmaschine (hOn-Gerät) mit Zustand aus .storage."""

    def __init__(self, mgr: "WasherManager", cfg: dict) -> None:
        self.mgr = mgr
        self.hass = mgr.hass
        self.id: str = cfg["id"]
        self.name: str = cfg.get("name") or "Waschmaschine"
        self.room: str = cfg.get("room") or self.id.split("_")[0]
        self.want_dev: str | None = cfg.get("hon_device")
        # Zwischenstecker (z. B. Tasmota) mit Leistungs-/Energiemessung – optional
        self.plug: dict = dict(cfg.get("plug") or {})
        self._unsub_plug = None
        self._last_sample = 0.0
        self.dev = None              # hOn HonDevice
        self.coord = None            # hOn Koordinator
        self.device_id: str | None = None
        self._unsub = None
        self._catalog: dict | None = None
        self.live: dict = {}         # aktueller Zustand für Sensor/Karte
        d = mgr.data.setdefault(self.id, {})
        d.setdefault("cycle", None)
        d.setdefault("done", None)
        d.setdefault("history", [])
        d.setdefault("favorites", ["hqd_cottons", "hqd_synthetic_and_coloured", "hqd_eco_40_60_degrees", "hqd_quick_15", "hqd_mix", "hqd_smart"])
        d.setdefault("last_params", {})
        d.setdefault("settings", {})
        d["settings"].setdefault("anti_crease", True)    # Knitterschutz nach Programmende standardmäßig an
        d["settings"].setdefault("price", 0.35)          # Strompreis €/kWh für die Kosten
        if "tasks" not in d:
            now = time.time()
            d["tasks"] = [dict(t, last=now, last_wash=None) for t in DEFAULT_TASKS]
        self.d = d

    # ---------------------------------------------------------------- hOn anbinden
    def attach(self) -> bool:
        if self.dev is not None:
            return True
        root = self.hass.data.get(HON) or {}
        reg = dr.async_get(self.hass)
        for key, hon in root.items():
            coords = getattr(hon, "_coordinator_dict", None)
            if not isinstance(coords, dict):
                continue
            for mac, coord in coords.items():
                dev = getattr(coord, "device", None)
                if dev is None or dev.appliance_type not in ("WM", "WD"):
                    continue
                did = None
                for de in reg.devices.values():
                    if any(len(i) >= 2 and i[0] == HON and i[1] == mac for i in de.identifiers):
                        did = de.id
                        break
                if self.want_dev and self.want_dev != did:
                    continue
                if any(w is not self and w.dev is dev for w in self.mgr.washers.values()):
                    continue
                self.dev, self.coord, self.device_id = dev, coord, did
                self._unsub = coord.async_add_listener(self._on_update)
                if self.plug.get("power") and not self._unsub_plug:
                    self._unsub_plug = async_track_state_change_event(self.hass, [self.plug["power"]], self._on_power)
                _LOGGER.info("washer_control: %s an hOn-Gerät %s (%s) gebunden", self.id, dev.name, mac)
                self._on_update()
                return True
        return False

    def detach(self) -> None:
        if self._unsub:
            self._unsub()
        self._unsub = None
        if self._unsub_plug:
            self._unsub_plug()
        self._unsub_plug = None

    # ---------------------------------------------------------------- Zwischenstecker (Leistung / Energie)
    def _plug_num(self, key: str) -> float | None:
        eid = self.plug.get(key)
        st = self.hass.states.get(eid) if eid else None
        return _num(st.state) if st and st.state not in ("unknown", "unavailable") else None

    def plug_view(self) -> dict:
        if not self.plug:
            return {}
        sw = self.hass.states.get(self.plug.get("switch") or "")
        return {"power": self._plug_num("power"), "energy_total": self._plug_num("energy"),
                "switch": self.plug.get("switch"), "on": (sw.state == "on") if sw else None, "entities": self.plug}

    @callback
    def _on_power(self, _ev=None) -> None:
        """Leistungskurve des laufenden Waschgangs aufzeichnen (höchstens alle 20 s, Sprünge sofort)."""
        cyc = self.d.get("cycle")
        w = self._plug_num("power")
        now = time.time()
        if w is None:
            return
        if cyc and cyc.get("start"):
            curve = cyc.setdefault("curve", [])
            last = curve[-1][1] if curve else None
            if now - self._last_sample >= 20 or last is None or abs(w - last) > max(30, last * .3):
                curve.append([round((now - cyc["start"]) / 60, 1), int(round(w))])
                self._last_sample = now
                if len(curve) > 600:      # sehr lange Programme: jeden zweiten Punkt verwerfen
                    cyc["curve"] = curve[::2]
            cyc["power_max"] = max(cyc.get("power_max") or 0, int(round(w)))
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _code_prog(self, code) -> str | None:
        if code is None:
            return None
        try:
            for p in self.catalog()["programs"]:
                if str(p.get("code")) == str(code):
                    return p["key"]
        except Exception:  # noqa: BLE001
            return None
        return None

    def _p(self) -> dict:
        try:
            return dict((self.dev.attributes or {}).get("parameters") or {})
        except Exception:  # noqa: BLE001
            return {}

    # ---------------------------------------------------------------- Zustand / Waschgang erkennen
    @callback
    def _on_update(self) -> None:
        if self.dev is None:
            return
        p = self._p()
        now = time.time()
        mode = _int(p.get("machMode"), 0)
        phase = str(p.get("prPhase", "0"))
        rem = _int(p.get("remainingTimeMM"), 0) or 0
        delay = _int(p.get("delayTime"), 0) or 0
        prog = None
        try:
            prog = self.dev.getProgramName()
        except Exception:  # noqa: BLE001
            prog = None
        if prog and prog.startswith("programs."):
            prog = prog.split(".")[-1]
        if prog and prog not in PROGRAMS and self._code_prog(p.get("prCode")):
            prog = self._code_prog(p.get("prCode"))
        if not prog:
            prog = self._code_prog(p.get("prCode"))     # Name fehlt (z. B. per App gestartet) → über den Programmcode
        # Knitterschutz: Trommel dreht nach Programmende in Abständen (loosenStatus / Phase 20 „Auflockern“)
        knitter = str(p.get("loosenStatus", "0")) == "1" or phase == "20"
        d = self.d
        cyc = d["cycle"]
        changed = False

        def num(k):
            return _num(p.get(k))

        # Programm ist durch, die Maschine meldet aber noch „läuft“ (Knitterschutz-Phase, Restzeit 0) → als fertig werten
        if cyc is not None and mode in RUN_MODES and cyc.get("start") and rem == 0 and (knitter or phase in ("0", "10")) \
                and now - cyc["start"] > 300:
            self._finish(cyc, "fertig", p, now)
            cyc = None
            changed = True
        after_done = d["done"] is not None and rem == 0 and (knitter or phase in ("0", "10"))
        if (mode in RUN_MODES and not after_done) or mode in PLAN_MODES:
            if cyc is None:
                pr_time = _int(p.get("prTime"), 0) or 0
                start = now
                if mode in RUN_MODES and pr_time and rem and pr_time > rem:   # HA lief beim Start nicht → Start schätzen
                    start = now - (pr_time - rem) * 60 if self.mgr.started_at and now - self.mgr.started_at < 300 else now
                cyc = d["cycle"] = {
                    "id": uuid.uuid4().hex[:10], "program": prog, "code": p.get("prCode"), "start": None if mode in PLAN_MODES else start,
                    "created": now, "planned_start": now + delay * 60 if mode in PLAN_MODES else None,
                    "temp": _int(p.get("temp")), "spin": _int(p.get("spinSpeed")), "rinse": _int(p.get("rinseIterations")),
                    "water0": num("totalWaterUsed"), "energy0": num("totalElectricityUsed"), "water": 0, "energy": 0, "weight": None,
                    "phases": [], "errors": [], "paused": 0, "plug0": self._plug_num("energy"), "curve": [],
                    "anti_crease": _int(p.get("permanentPressStatus")),
                }
                if d["done"]:
                    d["done"] = None
                changed = True
                self.hass.bus.async_fire(EVENT_STARTED, {"washer": self.id, "program": prog, "label": prog_label(prog)})
            if mode in RUN_MODES and not cyc.get("start"):
                cyc["start"] = now
                cyc["plug0"] = self._plug_num("energy")     # Energie der Steckdose ab dem echten Start (nicht ab Planung)
                changed = True
            if prog and cyc.get("program") != prog:
                cyc["program"] = prog
                changed = True
            for k, key in (("temp", "temp"), ("spin", "spinSpeed"), ("rinse", "rinseIterations")):
                v = _int(p.get(key))
                if v is not None and cyc.get(k) != v:
                    cyc[k] = v
            w = num("currentWaterUsed")
            e = num("currentElectricityUsed")
            kg = num("actualWeight") or num("weight")
            if w is not None and w > (cyc.get("water") or 0):
                cyc["water"] = w
            if e is not None and e > (cyc.get("energy") or 0):
                cyc["energy"] = e
            if kg:
                cyc["weight"] = kg
            kind = PHASE_KIND.get(phase)
            if kind and (not cyc["phases"] or cyc["phases"][-1] != kind):
                cyc["phases"].append(kind)
                changed = True
            if mode in RUN_MODES:
                end = now + rem * 60
            else:
                # Haier-Zeitvorwahl: delayTime = Minuten bis zum ENDE (ist sie kürzer als die Laufzeit, als Startverzögerung werten)
                end = now + (delay if delay >= rem else delay + rem) * 60
                cyc["planned_start"] = end - rem * 60
            if not cyc.get("end_est") or abs(cyc["end_est"] - end) > 90:
                cyc["end_est"] = end
                changed = True
            if mode == 3:
                cyc["paused"] = cyc.get("paused") or now
            elif cyc.get("paused"):
                cyc["paused"] = 0
        elif mode == 6 and cyc is not None:
            err = str(p.get("errors", ""))
            if err and err not in cyc["errors"]:
                cyc["errors"].append(err)
                changed = True
        elif cyc is not None and (mode in END_MODES or mode == 1) and not (mode in RUN_MODES):
            # mode 1 (Bereit) ohne vorheriges „Beendet“: mit Restzeit = abgebrochen
            result = "fertig" if mode in END_MODES or rem <= 1 else "abgebrochen"
            if cyc.get("start") is None and mode == 1:
                result = "abgebrochen"     # geplanter Start wurde verworfen
            self._finish(cyc, result, p, now)
            changed = True

        # Wäsche fertig → zurücksetzen, sobald die Tür geöffnet wird
        door_open = str(p.get("doorStatus", "0")) == "1"
        if d["done"] and door_open and now - d["done"]["at"] > 20:
            d["done"] = None
            changed = True

        self.live = {
            "mode": mode, "mode_name": MODES.get(str(mode), str(mode)), "phase": phase, "phase_name": PHASES.get(phase, phase),
            "phase_kind": PHASE_KIND.get(phase, "idle") if mode in RUN_MODES else "idle",
            "program": prog, "program_name": prog_label(prog), "code": p.get("prCode"),
            "remaining": rem if mode in RUN_MODES else ((delay if delay >= rem else delay + rem) if mode in PLAN_MODES else 0), "delay": delay,
            "temp": _int(p.get("temp")), "spin": _int(p.get("spinSpeed")), "rinse_left": _int(p.get("remainingRinseIterations")),
            "water": _num(p.get("currentWaterUsed")), "energy": _num(p.get("currentElectricityUsed")),
            "weight": _num(p.get("actualWeight")) or _num(p.get("weight")),
            "door_open": door_open, "door_locked": str(p.get("doorLockStatus", "0")) == "1",
            "child_lock": str(p.get("lockStatus", "0")) == "1", "remote": str(p.get("remoteCtrValid", "0")) == "1",
            "on": str(p.get("onOffStatus", "0")) == "1", "error": str(p.get("errors", "00") or "00"),
            "detergent": _num(p.get("detergentPercent")), "detergent_g": _num(p.get("haier_DetergentWeight")),
            "softener_g": _num(p.get("haier_SoftenerWeight")), "auto_detergent": _int(p.get("autoDetergentStatus")),
            "auto_softener": _int(p.get("autoSoftenerStatus")),
            # Tanks der Auto-Dosierung: die Maschine meldet nur „nachfüllen“ (detWarn/softWarn), keinen echten Füllstand
            "detergent_warn": str(p.get("detWarn", "0")) == "1" if "detWarn" in p else None,
            "softener_warn": str(p.get("softWarn", "0")) == "1" if "softWarn" in p else None,
            "total_cycles": max(0, (_int(p.get("totalWashCycle"), 1) or 1) - 1), "total_water": _num(p.get("totalWaterUsed")),
            "total_energy": _num(p.get("totalElectricityUsed")), "water_hardness": p.get("waterHard"),
            "connected": mode != 0, "updated": now, "anti_crease_active": knitter and mode not in PLAN_MODES,
            "anti_crease_option": _int(p.get("permanentPressStatus")),
        }
        pv = self.plug_view()
        if pv:
            self.live["power"] = pv.get("power")
            self.live["plug_on"] = pv.get("on")
            if d["cycle"] and d["cycle"].get("plug0") is not None and pv.get("energy_total") is not None:
                self.live["plug_kwh"] = round(max(0.0, pv["energy_total"] - d["cycle"]["plug0"]), 3)
        if changed:
            self.mgr.save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _finish(self, cyc: dict, result: str, p: dict, now: float) -> None:
        d = self.d
        w1, e1 = _num(p.get("totalWaterUsed")), _num(p.get("totalElectricityUsed"))
        water = cyc.get("water") or 0
        energy = cyc.get("energy") or 0
        if not water and w1 is not None and cyc.get("water0") is not None:
            water = max(0.0, w1 - cyc["water0"])
        if not energy and e1 is not None and cyc.get("energy0") is not None:
            energy = max(0.0, e1 - cyc["energy0"])
        start = cyc.get("start") or cyc.get("created") or now
        rec = {
            "id": cyc["id"], "program": cyc.get("program"), "name": prog_label(cyc.get("program")), "start": start, "end": now,
            "minutes": round((now - start) / 60), "temp": cyc.get("temp"), "spin": cyc.get("spin"), "rinse": cyc.get("rinse"),
            "water": round(water, 1), "energy": round(energy, 2), "weight": cyc.get("weight"), "result": result,
            "errors": cyc.get("errors") or [], "phases": cyc.get("phases") or [],
        }
        # Zwischenstecker: gemessene Energie + Leistungskurve (auf ≤ 96 Punkte verdichtet)
        e_now = self._plug_num("energy")
        if e_now is not None and cyc.get("plug0") is not None:
            rec["kwh_plug"] = round(max(0.0, e_now - cyc["plug0"]), 3)
        curve = cyc.get("curve") or []
        if curve:
            step = max(1, -(-len(curve) // 96))
            rec["curve"] = [[c[0], max(x[1] for x in curve[i:i + step])] for i, c in enumerate(curve) if i % step == 0]
            rec["power_max"] = cyc.get("power_max")
        rec["anti_crease"] = cyc.get("anti_crease")
        if result == "abgebrochen" and not cyc.get("start"):
            d["cycle"] = None          # nur geplant, nie gelaufen → nicht in den Verlauf
            return
        d["history"].insert(0, rec)
        del d["history"][HISTORY_MAX:]
        d["cycle"] = None
        if result == "fertig":
            d["done"] = {"at": now, "program": rec["program"], "name": rec["name"], "id": rec["id"], "anti_crease": rec.get("anti_crease")}
            # Wartung: Pflegeprogramme haken ihre Aufgabe automatisch ab
            for t in d["tasks"]:
                if rec["program"] and rec["program"] in (t.get("programs") or []):
                    t["last"] = now
                    t["last_wash"] = self._wash_no()
        self.hass.bus.async_fire(EVENT_FINISHED, {"washer": self.id, "result": result, **{k: rec[k] for k in ("program", "name", "minutes", "water", "energy")}})

    def _wash_no(self) -> int:
        n = self.live.get("total_cycles")
        return int(n) if n else len(self.d["history"])

    # ---------------------------------------------------------------- Ansichten
    def tasks_view(self) -> list[dict]:
        now = time.time()
        cur = self._wash_no()
        out = []
        for t in self.d["tasks"]:
            days = (now - (t.get("last") or now)) / 86400
            lw = t.get("last_wash")
            washes = (cur - lw) if lw is not None else self._washes_since(t.get("last"))
            ratio = 0.0
            if t.get("days"):
                ratio = max(ratio, days / t["days"])
            if t.get("washes"):
                ratio = max(ratio, washes / t["washes"])
            out.append({**t, "days_since": round(days, 1), "washes_since": washes, "ratio": round(ratio, 3), "due": ratio >= 1,
                        "soon": 0.85 <= ratio < 1})
        return out

    def _washes_since(self, ts: float | None) -> int:
        if not ts:
            return 0
        return sum(1 for h in self.d["history"] if h["end"] >= ts and h["result"] == "fertig")

    def stats(self) -> dict:
        H = [h for h in self.d["history"] if h.get("result") != "abgebrochen"]

        def _en(h):   # Energie: Messung der Steckdose bevorzugt, sonst Angabe der Maschine
            return h.get("kwh_plug") if h.get("kwh_plug") is not None else (h.get("energy") or 0)
        now = time.time()
        s: dict[str, Any] = {"count": len(H), "aborted": sum(1 for h in self.d["history"] if h.get("result") == "abgebrochen")}
        for days in (7, 30, 365):
            sub = [h for h in H if now - h["end"] < days * 86400]
            s[f"d{days}"] = {"count": len(sub), "water": round(sum(h.get("water") or 0 for h in sub), 1),
                             "energy": round(sum(_en(h) for h in sub), 2),
                             "minutes": sum(h.get("minutes") or 0 for h in sub)}
        if H:
            s["avg_minutes"] = round(sum(h.get("minutes") or 0 for h in H) / len(H))
            s["avg_water"] = round(sum(h.get("water") or 0 for h in H) / len(H), 1)
            s["avg_energy"] = round(sum(_en(h) for h in H) / len(H), 2)
            temps = [h["temp"] for h in H if h.get("temp") is not None]
            s["avg_temp"] = round(sum(temps) / len(temps)) if temps else None
        progs: dict[str, int] = {}
        for h in H:
            progs[h.get("program") or "?"] = progs.get(h.get("program") or "?", 0) + 1
        s["programs"] = sorted(([k, prog_label(k), v] for k, v in progs.items()), key=lambda x: -x[2])[:8]
        # gelernte Dauer je Programm (Mittel der letzten 5 fertigen Waschgänge) – hOn liefert keine Programmdauer
        pm: dict[str, list] = {}
        for h in H:
            if h.get("result") == "fertig" and h.get("program") and h.get("minutes"):
                pm.setdefault(h["program"], []).append(h["minutes"])
        s["prog_minutes"] = {k: round(sum(v[:5]) / len(v[:5])) for k, v in pm.items()}
        # letzte 12 Monate
        tz = dt_util.get_default_time_zone()
        today = datetime.now(tz)
        months = []
        for i in range(11, -1, -1):
            y, m = today.year, today.month - i
            while m <= 0:
                m += 12
                y -= 1
            months.append([y, m])
        mon = {f"{y}-{m:02d}": {"m": f"{y}-{m:02d}", "count": 0, "water": 0.0, "energy": 0.0} for y, m in months}
        for h in H:
            k = datetime.fromtimestamp(h["end"], tz).strftime("%Y-%m")
            if k in mon:
                mon[k]["count"] += 1
                mon[k]["water"] = round(mon[k]["water"] + (h.get("water") or 0), 1)
                mon[k]["energy"] = round(mon[k]["energy"] + _en(h), 2)
        s["months"] = list(mon.values())
        # letzte 30 Tage je Tag
        day0 = datetime(today.year, today.month, today.day, tzinfo=tz)
        dl = [{"d": (day0 - timedelta(days=i)).strftime("%Y-%m-%d"), "count": 0, "water": 0.0, "energy": 0.0} for i in range(29, -1, -1)]
        dmap = {x["d"]: x for x in dl}
        for h in H:
            k = datetime.fromtimestamp(h["end"], tz).strftime("%Y-%m-%d")
            if k in dmap:
                dmap[k]["count"] += 1
                dmap[k]["water"] = round(dmap[k]["water"] + (h.get("water") or 0), 1)
                dmap[k]["energy"] = round(dmap[k]["energy"] + _en(h), 2)
        s["days"] = dl
        s["price"] = self.d["settings"].get("price")
        # Wochentage / Uhrzeit (wann wird gewaschen)
        wd = [0] * 7
        hr = [0] * 24
        for h in H:
            t = datetime.fromtimestamp(h.get("start") or h["end"], tz)
            wd[t.weekday()] += 1
            hr[t.hour] += 1
        s["weekdays"] = wd
        s["hours"] = hr
        L = self.live
        s["lifetime"] = {"cycles": L.get("total_cycles"), "water": L.get("total_water"), "energy": L.get("total_energy")}
        return s

    def cycle_view(self) -> dict | None:
        c = self.d["cycle"]
        if not c:
            return None
        now = time.time()
        start = c.get("start")
        end = c.get("end_est")
        prog = None
        if start and end and end > start:
            prog = max(0.0, min(1.0, (now - start) / (end - start)))
        return {"id": c["id"], "program": c.get("program"), "name": prog_label(c.get("program")), "start": _iso(start),
                "planned_start": _iso(c.get("planned_start")) if not start else None, "end": _iso(end), "progress": prog,
                "temp": c.get("temp"), "spin": c.get("spin"), "water": c.get("water"), "energy": c.get("energy"),
                "weight": c.get("weight"), "phases": c.get("phases"), "paused_since": _iso(c.get("paused") or None),
                "errors": c.get("errors"), "curve": c.get("curve") or [], "power_max": c.get("power_max"),
                "plug_kwh": self.live.get("plug_kwh"), "anti_crease": c.get("anti_crease")}

    def done_view(self) -> dict | None:
        dn = self.d["done"]
        if not dn:
            return None
        return {**dn, "at": _iso(dn["at"]), "minutes_ago": round((time.time() - dn["at"]) / 60)}

    def snapshot(self, history: int = 30) -> dict:
        return {
            "id": self.id, "name": self.name, "room": self.room, "device_id": self.device_id, "attached": self.dev is not None,
            "model": getattr(self.dev, "model_name", None) if self.dev else None, "live": self.live, "cycle": self.cycle_view(),
            "done": self.done_view(), "tasks": self.tasks_view(), "stats": self.stats(),
            "history": [dict(h, start=_iso(h.get("start")), end=_iso(h.get("end"))) for h in self.d["history"][:history]],
            "favorites": self.d["favorites"], "last_params": self.d["last_params"], "commands": self.commands(), "version": VERSION,
            "settings": self.d["settings"], "plug": self.plug_view(),
        }

    def state(self) -> str:
        if self.dev is None:
            return "unavailable"
        m = self.live.get("mode")
        if self.d["done"] and m not in RUN_MODES and m not in PLAN_MODES:
            return "fertig"
        return {0: "getrennt", 1: "bereit", 2: "laeuft", 3: "pausiert", 4: "geplant", 5: "geplant", 6: "fehler", 7: "beendet",
                8: "test", 9: "beendet"}.get(m, "aus" if not self.live.get("on") else "bereit")

    # ---------------------------------------------------------------- Programme / Befehle
    def commands(self) -> list[str]:
        return list((self.dev.commands or {}).keys()) if self.dev else []

    def catalog(self) -> dict:
        if self._catalog is not None:
            return self._catalog
        if self.dev is None:
            raise ValueError("Waschmaschine nicht verbunden (hOn)")
        cmd = self.dev.commands.get("startProgram")
        if cmd is None:
            raise ValueError("hOn liefert keine Programme (startProgram fehlt)")
        out = []
        for name, pc in (cmd.get_programs() or {}).items():
            params, fixed = {}, {}
            for k, prm in (pc.parameters or {}).items():
                if k == "program":
                    continue
                if hasattr(prm, "min") and hasattr(prm, "step"):
                    params[k] = {"t": "range", "min": prm.min, "max": prm.max, "step": prm.step, "default": prm.default}
                elif hasattr(prm, "values") and hasattr(prm, "default"):
                    vals = prm.values
                    try:
                        vals = sorted(vals, key=lambda x: float(x))
                    except (TypeError, ValueError):
                        pass
                    params[k] = {"t": "enum", "values": vals, "default": prm.default}
                else:
                    fixed[k] = prm.value
            anc = {}
            try:
                for k, v in (pc.ancillary_parameters or {}).items():
                    if isinstance(v, (str, int, float)) and len(str(v)) < 40:
                        anc[k] = v
            except Exception:  # noqa: BLE001
                pass
            lab, grp = PROGRAMS.get(name, (prog_label(name), "geraet" if name.startswith("hqd_") else "alltag"))
            out.append({"key": name, "name": lab, "group": grp, "code": fixed.get("prCode"), "time": _int(fixed.get("prTime")),
                        "params": params, "fixed": fixed, "anc": anc})
        self._catalog = {"programs": out, "groups": GROUPS}
        return self._catalog

    async def async_start(self, program: str, params: dict) -> dict:
        if self.dev is None:
            raise ValueError("Waschmaschine nicht verbunden (hOn)")
        if not self.live.get("remote"):
            raise ValueError("Fernstart ist an der Maschine nicht aktiv – an der Maschine die Fernbedienung (WLAN-Taste) einschalten.")
        if self.live.get("mode") in RUN_MODES:
            raise ValueError("Es läuft bereits ein Programm.")
        cat = {p["key"]: p for p in self.catalog()["programs"]}
        if program not in cat:
            raise ValueError(f"Unbekanntes Programm: {program}")
        allowed = cat[program]["params"]
        clean = {}
        for k, v in (params or {}).items():
            if k in allowed:
                clean[k] = str(v)
        if _int(clean.get("delayTime"), 0):
            clean["delayStatus"] = "1"
        elif "delayStatus" in allowed:
            clean["delayStatus"] = "0"
        command = self.dev.start_command(program, clean)
        ok = await command.send()
        if not ok:
            raise ValueError("hOn hat den Startbefehl abgelehnt (Tür zu? Fernstart aktiv? Programm am Gerät erlaubt?)")
        self.d["last_params"][program] = {k: v for k, v in clean.items() if k not in ("delayTime", "delayStatus")}
        self.mgr.save()
        await self.coord.async_request_refresh()
        return {"ok": True}

    async def async_command(self, what: str) -> dict:
        if self.dev is None:
            raise ValueError("Waschmaschine nicht verbunden (hOn)")
        names = {"pause": ["pauseProgram"], "resume": ["resumeProgram"], "stop": ["stopProgram"]}.get(what)
        if names is None:
            raise ValueError(f"Unbekannter Befehl: {what}")
        for n in names:
            cmd = self.dev.commands.get(n)
            if cmd is not None:
                try:
                    self.dev.update_command(cmd, self._p())
                except Exception:  # noqa: BLE001
                    pass
                ok = await cmd.send()
                if not ok:
                    raise ValueError(f"hOn hat „{what}“ abgelehnt")
                await self.coord.async_request_refresh()
                return {"ok": True, "command": n}
        if what == "stop":
            await self.coord.async_set({"onOffStatus": "0", "machMode": "1"})
            await self.coord.async_request_refresh()
            return {"ok": True, "command": "onOff"}
        raise ValueError(f"Die Maschine unterstützt „{what}“ nicht per hOn")

    async def async_refresh(self) -> None:
        if self.coord is not None:
            await self.coord.async_request_refresh()


class WasherManager:
    def __init__(self, hass: HomeAssistant, devices: list[dict]) -> None:
        self.hass = hass
        self.store: Store = Store(hass, STORE_VERSION, STORE_KEY)
        self.data: dict = {}
        self.cfgs = devices
        self.washers: dict[str, Washer] = {}
        self.started_at: float | None = None
        self._unsub_tick = None

    async def async_start(self) -> None:
        self.data = (await self.store.async_load()) or {}
        self.started_at = time.time()
        for c in self.cfgs:
            self.washers[c["id"]] = Washer(self, c)
        self._try_attach()
        self._unsub_tick = async_track_time_interval(self.hass, self._tick, timedelta(seconds=30))

    @callback
    def _try_attach(self) -> None:
        for w in self.washers.values():
            w.attach()

    @callback
    def _tick(self, _now=None) -> None:
        # hOn lädt evtl. nach uns → so lange verbinden versuchen; sonst Sensoren für Restzeit/Fortschritt auffrischen
        if any(w.dev is None for w in self.washers.values()):
            self._try_attach()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def get(self, wid: str | None) -> Washer:
        if not wid:
            return next(iter(self.washers.values()))
        if wid not in self.washers:
            raise ValueError(f"Waschmaschine {wid} unbekannt")
        return self.washers[wid]

    @callback
    def save(self) -> None:
        self.store.async_delay_save(lambda: self.data, 2)

    # ---------------------------------------------------------------- Einstellungen / Wartung
    async def async_settings(self, wid: str, s: dict) -> dict:
        w = self.get(wid)
        for k in ("anti_crease",):
            if k in s:
                w.d["settings"][k] = bool(s[k])
        if "price" in s:
            w.d["settings"]["price"] = max(0.0, float(_num(s["price"], 0) or 0))
        if "favorites" in s:
            w.d["favorites"] = [str(x) for x in s["favorites"]][:24]
        self.save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        return {"favorites": w.d["favorites"], "settings": w.d["settings"]}

    async def async_task(self, wid: str, action: str, task: dict) -> list:
        w = self.get(wid)
        T = w.d["tasks"]
        tid = task.get("id")
        if action == "done":
            for t in T:
                if t["id"] == tid:
                    t["last"] = time.time()
                    t["last_wash"] = w._wash_no()
                    break
            else:
                raise ValueError("Aufgabe nicht gefunden")
        elif action == "save":
            t0 = next((t for t in T if t["id"] == tid), None)
            if t0 is None:
                tid = tid or uuid.uuid4().hex[:8]
                t0 = {"id": tid, "last": time.time(), "last_wash": w._wash_no(), "programs": [], "icon": "tool"}
                T.append(t0)
            for k in ("name", "hint", "icon"):
                if k in task:
                    t0[k] = str(task[k])[:300]
            for k in ("washes", "days"):
                if k in task:
                    t0[k] = max(0, int(_num(task[k], 0) or 0))
            if "programs" in task:
                t0["programs"] = [str(x) for x in task["programs"]]
        elif action == "delete":
            w.d["tasks"] = [t for t in T if t["id"] != tid]
        elif action == "reset":
            w.d["tasks"] = [dict(t, last=time.time(), last_wash=w._wash_no()) for t in DEFAULT_TASKS]
        else:
            raise ValueError("Unbekannte Aktion")
        self.save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
        return w.tasks_view()

    async def async_ack(self, wid: str) -> None:
        w = self.get(wid)
        w.d["done"] = None
        self.save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_history_delete(self, wid: str, hid: str) -> None:
        w = self.get(wid)
        w.d["history"] = [h for h in w.d["history"] if h["id"] != hid]
        self.save()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_stop(self) -> None:
        if self._unsub_tick:
            self._unsub_tick()
        for w in self.washers.values():
            w.detach()
        await self.store.async_save(self.data)
