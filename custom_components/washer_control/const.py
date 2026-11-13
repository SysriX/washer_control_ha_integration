"""Konstanten der Waschmaschinen-Steuerung (washer_control)."""

DOMAIN = "washer_control"
VERSION = "1.1.1"

STORE_KEY = "washer_control"
STORE_VERSION = 1

SIGNAL_UPDATE = "washer_control_update"
EVENT_FINISHED = "washer_control_finished"     # Waschgang fertig (für Automationen / Benachrichtigungen)
EVENT_STARTED = "washer_control_started"

HISTORY_MAX = 500          # so viele Waschgänge merken
HON = "hon"

# machMode der hOn-Waschmaschine
MODES = {"0": "Getrennt", "1": "Bereit", "2": "Läuft", "3": "Pausiert", "4": "Geplant", "5": "Geplant (Pause)",
         "6": "Fehler", "7": "Beendet", "8": "Test", "9": "Beendet"}
RUN_MODES = {2, 3}
PLAN_MODES = {4, 5}
END_MODES = {7, 9}

# prPhase (aus hOn translations/de.json)
PHASES = {"0": "Bereit", "1": "Waschen", "2": "Waschen", "3": "Schleudern", "4": "Spülen", "5": "Spülen", "6": "Spülen",
          "7": "Trocknen", "8": "Trocknen", "9": "Dampf", "10": "Bereit", "11": "Schleudern", "12": "Wiegen", "13": "Wiegen",
          "14": "Waschen", "15": "Waschen", "16": "Waschen", "17": "Spülen", "18": "Spülen", "19": "Geplant", "20": "Auflockern",
          "24": "Aktualisieren", "25": "Waschen", "26": "Heizen", "27": "Waschen"}
# grobe Phase für die Grafik: wash / rinse / spin / weigh / steam / dry / heat / idle
PHASE_KIND = {"1": "wash", "2": "wash", "3": "spin", "4": "rinse", "5": "rinse", "6": "rinse", "7": "dry", "8": "dry", "9": "steam",
              "11": "spin", "12": "weigh", "13": "weigh", "14": "wash", "15": "wash", "16": "wash", "17": "rinse", "18": "rinse",
              "20": "tumble", "25": "wash", "26": "heat", "27": "wash"}

# Deutsche Programmnamen + Gruppe (geraet = direkt am Gerät, sonst App-Programme)
PROGRAMS = {
    "hqd_smart": ("Smart", "geraet"), "hqd_quick_15": ("Schnell 15'", "geraet"), "hqd_spin": ("Schleudern", "geraet"),
    "hqd_cottons": ("Baumwolle", "geraet"), "hqd_synthetic_and_coloured": ("Synthetik & Bunt", "geraet"),
    "hqd_handwash_wool": ("Hand- & Wollwäsche", "geraet"), "hqd_20_degrees": ("20 °C", "geraet"),
    "hqd_eco_40_60_degrees": ("Eco 40-60", "geraet"), "hqd_shirts": ("Hemden", "geraet"), "hqd_babycare": ("Babypflege", "geraet"),
    "hqd_delicate_cradle": ("Feinwäsche", "geraet"), "hqd_allergy": ("Allergie", "geraet"), "hqd_refresh": ("Auffrischen", "geraet"),
    "hqd_duvet": ("Bettdecken", "geraet"), "hqd_autoclean": ("Trommelreinigung", "pflege"), "hqd_sport": ("Sport", "geraet"),
    "hqd_checkup": ("Selbsttest", "pflege"), "hqd_quick_wash_57": ("Schnell 57'", "geraet"), "hqd_rinse": ("Spülen", "geraet"),
    "hqd_mix": ("Mix", "geraet"),
    "iot_wash_cotton": ("Baumwolle", "alltag"), "iot_wash_synthetic": ("Synthetik", "alltag"), "iot_wash_mixed": ("Mischwäsche", "alltag"),
    "iot_wash_delicate": ("Feinwäsche", "alltag"), "iot_wash_coloured": ("Buntwäsche", "alltag"), "iot_wash_wool": ("Wolle", "textil"),
    "iot_wash_rapid_14": ("Kurz 14'", "kurz"), "iot_wash_rapid_30": ("Kurz 30'", "kurz"), "iot_wash_rapid_44": ("Kurz 44'", "kurz"),
    "iot_wash_rapid_59": ("Kurz 59'", "kurz"), "iot_wash_sport": ("Sport", "textil"), "iot_wash_spin": ("Schleudern", "alltag"),
    "iot_wash_rinse": ("Spülen", "alltag"), "iot_wash_baby_sanitizer": ("Baby Hygiene", "hygiene"), "iot_wash_backpacks": ("Rucksäcke", "textil"),
    "iot_wash_bathrobe": ("Bademäntel", "textil"), "iot_wash_bed_linen": ("Bettwäsche", "alltag"), "iot_wash_cashmere": ("Kaschmir", "textil"),
    "iot_wash_cuddly_toys": ("Kuscheltiere", "textil"), "iot_wash_curtains": ("Gardinen", "textil"), "iot_wash_diving_suits": ("Neopren", "textil"),
    "iot_wash_down_jackets": ("Daunenjacken", "textil"), "iot_wash_delicate_tablecloths": ("Feine Tischdecken", "textil"),
    "iot_wash_denim_jeans": ("Jeans", "textil"), "iot_wash_chocolate_stains": ("Schokoflecken", "flecken"),
    "iot_wash_wine_stains": ("Weinflecken", "flecken"), "iot_wash_fruit_stains": ("Obstflecken", "flecken"),
    "iot_wash_blood_stains": ("Blutflecken", "flecken"), "iot_wash_perfect_white": ("Perfektes Weiß", "flecken"),
    "iot_wash_colored_anti_stain": ("Bunt Anti-Flecken", "flecken"), "iot_wash_bleaching": ("Bleichen", "flecken"),
    "iot_wash_anti_mites": ("Anti-Milben", "hygiene"), "iot_wash_anti_odor": ("Anti-Geruch", "hygiene"), "iot_wash_pets": ("Haustiere", "hygiene"),
    "iot_wash_delicate_antiallergy": ("Fein Anti-Allergie", "hygiene"), "iot_wash_new_clothes": ("Neue Kleidung", "textil"),
    "iot_wash_lingerie": ("Dessous", "textil"), "iot_wash_mats": ("Matten & Vorleger", "textil"), "iot_wash_trainers": ("Turnschuhe", "textil"),
    "iot_wash_men_s_trousers": ("Herrenhosen", "textil"), "iot_wash_silk": ("Seide", "textil"), "iot_wash_ski_suit": ("Skianzug", "textil"),
    "iot_wash_delicate_colors": ("Feine Farben", "alltag"), "iot_wash_dark": ("Dunkles", "alltag"),
    "iot_wash_swimsuits_and_bikinis": ("Badebekleidung", "textil"), "iot_wash_tablecloths": ("Tischdecken", "textil"),
    "iot_wash_technical_fabrics": ("Funktionsstoffe", "textil"), "iot_wash_technical_jackets": ("Funktionsjacken", "textil"),
    "iot_wash_masks_sanification": ("Masken Hygiene", "hygiene"), "iot_wash_masks_refresh": ("Masken Auffrischen", "hygiene"),
    "iot_wash_cold_wash": ("Kaltwäsche", "alltag"), "iot_wash_colored": ("Bunt", "alltag"), "iot_wash_colored_delicate": ("Bunt fein", "alltag"),
    "iot_wash_delicate_dark": ("Dunkles fein", "alltag"), "iot_wash_delicate_whites": ("Weißes fein", "alltag"),
    "iot_wash_handwash": ("Handwäsche", "textil"), "iot_wash_handwash_colored": ("Handwäsche bunt", "textil"),
    "iot_wash_handwash_dark": ("Handwäsche dunkel", "textil"), "iot_wash_resistant_colored": ("Bunt robust", "alltag"),
    "iot_wash_resistant_dark": ("Dunkles robust", "alltag"), "iot_wash_resistant_whites": ("Weißes robust", "alltag"),
    "iot_wash_whites": ("Weißwäsche", "alltag"), "iot_wash_ariel_cold_cycle": ("Ariel Kalt", "marke"),
    "iot_wash_dash_cold_cycle": ("Dash Kalt", "marke"), "iot_wash_ariel_fresh_cycle": ("Ariel Frische", "marke"),
    "iot_wash_dash_fresh_cycle": ("Dash Frische", "marke"), "iot_wash_ariel_clean_cycle": ("Ariel Sauber", "marke"),
    "iot_wash_dash_clean_cycle": ("Dash Sauber", "marke"), "iot_wash_pets_hair_removal": ("Tierhaare entfernen", "hygiene"),
    "iot_wash_pets_odours_stains_removal": ("Tiergeruch & Flecken", "hygiene"),
    "iot_wash_quick_drum_cleaner": ("Schnelle Trommelreinigung", "pflege"), "iot_wash_tennis_tie_break": ("Tennis Tie-Break", "textil"),
}
GROUPS = {"geraet": "Am Gerät", "alltag": "Alltag", "kurz": "Kurzprogramme", "textil": "Spezielle Textilien", "flecken": "Flecken",
          "hygiene": "Hygiene", "marke": "Waschmittel-Programme", "pflege": "Pflege der Maschine"}

# Wartungsaufgaben, die beim ersten Start angelegt werden (änderbar im Dashboard)
DEFAULT_TASKS = [
    {"id": "trommel", "name": "Trommelreinigung", "icon": "drum", "washes": 30, "days": 60,
     "programs": ["hqd_autoclean", "iot_wash_quick_drum_cleaner"],
     "hint": "Programm „Trommelreinigung“ leer laufen lassen (ggf. mit Maschinenreiniger). Wird automatisch abgehakt."},
    {"id": "filter", "name": "Flusensieb / Pumpenfilter", "icon": "filter", "washes": 60, "days": 90, "programs": [],
     "hint": "Klappe unten öffnen, Restwasser über den Schlauch ablassen, Filter herausdrehen, ausspülen, fest eindrehen."},
    {"id": "schublade", "name": "Waschmittelschublade", "icon": "drawer", "washes": 30, "days": 60, "programs": [],
     "hint": "Schublade ganz herausziehen, Einsätze warm ausspülen, Schacht mit Bürste reinigen."},
    {"id": "dichtung", "name": "Türdichtung", "icon": "seal", "washes": 20, "days": 30, "programs": [],
     "hint": "Gummimanschette inkl. Falz auswischen, Fremdkörper entfernen; Tür nach dem Waschen angelehnt lassen."},
    {"id": "entkalken", "name": "Entkalken", "icon": "drop", "washes": 0, "days": 180, "programs": [],
     "hint": "Entkalker nach Packungsangabe im Programm Baumwolle 60 °C ohne Wäsche laufen lassen."},
]
