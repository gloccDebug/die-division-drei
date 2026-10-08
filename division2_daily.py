from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import requests


# =========================
# Configuration
# =========================

DIVISION2_URL = os.getenv(
    "DIVISION2_URL",
    "https://hi-dep.github.io/division2/?view=event&lang=en",
)
EVENT_INDEX_URL = os.getenv(
    "EVENT_INDEX_URL",
    "https://hi-dep.github.io/division2/data/event/index.json",
)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

EMBED_COLOR = int(os.getenv("EMBED_COLOR", str(0xE67E22)))
EMBED_FOOTER = os.getenv("EMBED_FOOTER", "Die Division Drei • SHD Intel")
EMBED_USERNAME = os.getenv("EMBED_USERNAME", "ISAC – Die Division Drei")

USER_AGENT = os.getenv(
    "USER_AGENT",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def fetch_json(url: str) -> Dict:
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("Event index returned invalid JSON.") from exc

MISSION_LABELS = {
    "the art museum": "Kunstmuseum",
    "capitol building": "Kapitol",
    "jefferson plaza": "Jefferson Plaza",
    "lincoln memorial": "Lincoln Memorial",
    "federal emergency bunker": "Notfallbunker des Bundes",
}


TOKEN_LABELS = {
    # Waffen
    "ar": "Sturmgewehr",
    "lmg": "LMG",
    "mmr": "Präzisionsgewehr",
    "pistol": "Pistole",
    "rifle": "Gewehr",
    "shotgun": "Schrotflinte",
    "smg": "MP",

    # Ausrüstungsteile
    "mask": "Maske",
    "backpack": "Rucksack",
    "chest": "Brustschutz",
    "gloves": "Handschuhe",
    "holster": "Holster",
    "kneepads": "Knieschoner",
}


# ==========================================================
# DEUTSCHE NAMEN DER AUSRÜSTUNGSGARNITUREN
# Nur Namen eintragen, die sicher belegt sind.
# Unbekannte Namen bleiben automatisch Englisch.
# ==========================================================

GEAR_SET_LABELS = {
    # Striker's Battlegear
    "striker's battlegear": "Kampfausrüstung des Stürmers",
    "strikers battlegear": "Kampfausrüstung des Stürmers",

    "core strength": "Rumpfstärke",

    # Aces & Eights
    "aces & eights": "Asse und Achten",

    # Hunter's Fury
    "hunter's fury": "Zorn des Jägers",
    "hunters fury": "Zorn des Jägers",

    # Foundry Bulwark
    "foundry bulwark": "Gießerei-Bollwerk",

    # Future Initiative
    "future initiative": "Zukunftsinitiative",
}


def normalize_label(value: str) -> str:
    raw = str(value or "").strip()

    if not raw:
        return "N/A"

    # Waffen / Ausrüstungsteile
    token_result = TOKEN_LABELS.get(raw.lower())
    if token_result:
        return token_result

    # Ausstattungsgarnituren
    gear_result = GEAR_SET_LABELS.get(raw.lower())
    if gear_result:
        return gear_result

    # Alles, was wir noch nicht sicher übersetzt haben,
    # bleibt im originalen englischen Namen.
    return raw


CACHE_LABELS = {
    "prototype gear cache": "Prototyp-Ausrüstungskiste",
    "prototype weapon cache": "Prototyp-Waffenkiste",
}


def normalize_cache_label(value: str) -> str:
    raw = str(value or "").strip()

    if not raw:
        return "N/A"

    return CACHE_LABELS.get(raw.lower(), raw)



def build_table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def fmt_row(cols: List[str]) -> str:
        return " | ".join(c.ljust(widths[idx]) for idx, c in enumerate(cols))

    sep = "-+-".join("-" * w for w in widths)
    lines = [fmt_row(headers), sep]
    lines.extend(fmt_row(r) for r in rows)
    return "```\n" + "\n".join(lines) + "\n```"


def pick_escalation_snapshot(data: Dict, target_day: str) -> Tuple[str, str, List[List[str]], List[List[str]]]:
    escalation_list = data.get("Escalation")
    if not isinstance(escalation_list, list) or not escalation_list:
        raise RuntimeError("Escalation data is missing from event index.")

    entries = [e for e in escalation_list if isinstance(e, dict)]
    if not entries:
        raise RuntimeError("Escalation entries are invalid.")

    # Prefer exact day match, otherwise fall back to latest available target_loot_by_day entry.
    chosen_week = None
    chosen_day = None
    chosen_missions: List[str] = []
    chosen_loot: List[str] = []
    gear_cache = ""
    weapon_cache = ""

    for entry in entries:
        missions = entry.get("missions")
        rows = entry.get("target_loot_by_day")
        if not isinstance(missions, list) or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = str(row.get("day", "")).strip()
            if day != target_day:
                continue
            chosen_week = str(entry.get("week", "")).strip()
            chosen_day = day
            chosen_missions = [str(m).strip() for m in missions]
            chosen_loot = [normalize_label(v) for v in row.get("target_loot", [])]
            gear_cache = normalize_cache_label(
            str(row.get("prototype_gear_cache", "")).strip()
            )

            weapon_cache = normalize_cache_label(
            str(row.get("prototype_weapon_cache", "")).strip()
            )
            
            break
        if chosen_day:
            break

    if not chosen_day:
        latest = None
        for entry in entries:
            missions = entry.get("missions")
            rows = entry.get("target_loot_by_day")
            if not isinstance(missions, list) or not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                day = str(row.get("day", "")).strip()
                if not day:
                    continue
                candidate = (day, entry, row)
                if latest is None or day > latest[0]:
                    latest = candidate

        if latest is None:
            raise RuntimeError("No daily target loot rows found in escalation data.")

        _, entry, row = latest
        chosen_week = str(entry.get("week", "")).strip()
        chosen_day = str(row.get("day", "")).strip()
        chosen_missions = [str(m).strip() for m in entry.get("missions", [])]
        chosen_loot = [normalize_label(v) for v in row.get("target_loot", [])]
        gear_cache = normalize_label(
        str(row.get("prototype_gear_cache", "")).strip()
)

weapon_cache = normalize_label(
    str(row.get("prototype_weapon_cache", "")).strip()
)

    mission_rows: List[List[str]] = []
    max_len = min(len(chosen_missions), len(chosen_loot))

    for i in range(max_len):
        mission_rows.append([
            str(i + 1),
            chosen_missions[i],
            chosen_loot[i]
        ])

    vendor_rows = [
        ["1", "Ausrüstungskiste", gear_cache],
        ["2", "Waffenkiste", weapon_cache],
    ]

    return chosen_week, chosen_day, mission_rows, vendor_rows


def build_discord_embed(week: str, target_day: str, mission_rows: List[List[str]], vendor_rows: List[List[str]]) -> Dict:
    mission_table = build_table(["#", "Mission", "Zielbeute"], mission_rows)
    vendor_table = build_table(["#", "Typ", "Angebot"], vendor_rows)

    return {
        "title": "🎯 Tägliche Zielbeute",
        "description": f"📅 Woche: {week} / Zielbeute: {target_day}",
        "color": EMBED_COLOR,
        "timestamp": utc_now().isoformat(),
        "footer": {"text": EMBED_FOOTER},
        "fields": [
            {
                "name": "☠️ Eskalation Zielbeute",
                "value": truncate(mission_table, 1024),
                "inline": False,
            },
            {
                "name": "🛒 Eskalation / Prototyp Händler",
                "value": truncate(vendor_table, 1024),
                "inline": False,
            },
            {
                "name": "Source",
                "value": "https://hi-dep.github.io/division2/?view=event&lang=en",
                "inline": False,
            },
        ],
    }


def send_webhook(embed: Dict) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")

    payload = {
        "username": EMBED_USERNAME,
        "embeds": [embed],
    }

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()


def main() -> int:
    try:
        today = utc_now().strftime("%Y-%m-%d")
        data = fetch_json(EVENT_INDEX_URL)
        week, target_day, mission_rows, vendor_rows = pick_escalation_snapshot(data, today)
        embed = build_discord_embed(week, target_day, mission_rows, vendor_rows)
        send_webhook(embed)
        print("Webhook sent successfully.")
        return 0
    except Exception as exc:
        print(f"Job failed: {exc}", file=sys.stderr)
        try:
            if DISCORD_WEBHOOK_URL:
                error_embed = {
                    "title": "Division 2 Daily Reset - Error",
                    "description": truncate(f"Scrape/send failed: {exc}", 4000),
                    "color": 0xE74C3C,
                    "timestamp": utc_now().isoformat(),
                    "footer": {"text": EMBED_FOOTER},
                }
                send_webhook(error_embed)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
