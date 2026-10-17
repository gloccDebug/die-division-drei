import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
EVENT_INDEX_URL = os.environ.get(
    "EVENT_INDEX_URL",
    "https://hi-dep.github.io/division2/data/event/index.json",
).strip()
EMBED_FOOTER = os.environ.get("EMBED_FOOTER", "Escalation Target Loot")
EMBED_USERNAME = os.environ.get("EMBED_USERNAME", "Escalation Target Loot")
MESSAGE_ID_FILE = "last_discord_message_id.txt"
REQUEST_TIMEOUT = 15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def fetch_json(url: str) -> Dict[str, Any]:
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def pick_escalation_snapshot(
    data: Dict[str, Any], today_str: str
) -> Tuple[str, str, List[Tuple[str, str]], List[Tuple[str, str]]]:
    escalation_list = data.get("Escalation", [])
    if not escalation_list:
        raise ValueError("Keine Escalation-Daten im JSON gefunden.")

    # Neuesten bzw. passenden Block ermitteln
    selected_block = escalation_list[-1]
    week = str(selected_block.get("week", "Unbekannt"))
    missions: List[str] = selected_block.get("missions", [])

    daily_loot_entries = selected_block.get("target_loot_by_day", [])
    if not daily_loot_entries:
        raise ValueError("Keine täglichen Loot-Einträge gefunden.")

    # Passenden Tag suchen oder auf den letzten verfügbaren Tag zurückfallen
    matching_day_entry: Optional[Dict[str, Any]] = None
    for entry in daily_loot_entries:
        if entry.get("day") == today_str:
            matching_day_entry = entry
            break

    if not matching_day_entry:
        matching_day_entry = daily_loot_entries[-1]

    target_day = str(matching_day_entry.get("day", today_str))
    loot_items = matching_day_entry.get("target_loot", [])

    mission_rows: List[Tuple[str, str]] = []
    for idx, mission in enumerate(missions):
        loot = loot_items[idx] if idx < len(loot_items) else ""
        mission_rows.append((mission, loot))

    # Caches / Vendor Rows
    vendor_rows: List[Tuple[str, str]] = []
    gear_cache = matching_day_entry.get("prototype_gear_cache")
    if gear_cache:
        vendor_rows.append(("Prototype Gear Cache", str(gear_cache).upper()))

    weapon_cache = matching_day_entry.get("prototype_weapon_cache")
    if weapon_cache:
        vendor_rows.append(("Prototype Weapon Cache", str(weapon_cache).upper()))

    return week, target_day, mission_rows, vendor_rows


def build_discord_embed(week, target_day, mission_rows, vendor_rows) -> Dict[str, Any]:
    fields = []
    if mission_rows:
        fields.append({
            "name": "Missions / Target Loot",
            "value": truncate("\n".join(
                f"**{name}**" + (f" — {detail}" if detail else "")
                for name, detail in mission_rows
            ), 1024),
            "inline": False,
        })
    if vendor_rows:
        fields.append({
            "name": "Vendors",
            "value": truncate("\n".join(
                f"**{name}**" + (f" — {detail}" if detail else "")
                for name, detail in vendor_rows
            ), 1024),
            "inline": False,
        })
    if not fields:
        fields.append({
            "name": "Hinweis",
            "value": "Für heute wurden keine Missions- oder Händlerdaten erkannt.",
            "inline": False,
        })
    return {
        "title": f"Division 2 Escalation Target Loot — {target_day}",
        "description": f"Übersicht für **{target_day}** (Woche: **{week}**).",
        "color": 0xE67E22,
        "fields": fields,
        "timestamp": utc_now().isoformat(),
        "footer": {"text": EMBED_FOOTER},
    }


def send_webhook(embed: Dict[str, Any], replace_previous: bool = True) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("Die Umgebungsvariable DISCORD_WEBHOOK_URL ist nicht gesetzt.")

    message_id_file = MESSAGE_ID_FILE
    old_message_id = None

    if replace_previous:
        try:
            with open(message_id_file, "r", encoding="utf-8") as file:
                old_message_id = file.read().strip()
        except FileNotFoundError:
            pass

        if old_message_id:
            delete_url = f"{DISCORD_WEBHOOK_URL.rstrip('/')}/messages/{old_message_id}"
            delete_response = requests.delete(delete_url, timeout=REQUEST_TIMEOUT)
            if delete_response.status_code not in (200, 204, 404):
                delete_response.raise_for_status()

    separator = "&" if "?" in DISCORD_WEBHOOK_URL else "?"
    post_url = f"{DISCORD_WEBHOOK_URL}{separator}wait=true"

    payload = {
        "username": EMBED_USERNAME,
        "embeds": [embed],
    }

    response = requests.post(
        post_url,
        json=payload,
        timeout=REQUEST_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()

    try:
        new_message_id = str(response.json()["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Discord hat keine Nachrichten-ID zurückgegeben.") from exc

    # GitHub Actions muss diese Datei nach dem Lauf ins Repository committen.
    with open(message_id_file, "w", encoding="utf-8") as file:
        file.write(new_message_id)

    print(f"Discord-Nachricht gesendet. ID: {new_message_id}")


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
                    "title": "Division 2 Daily Reset - Fehler",
                    "description": truncate(f"Fehler beim Abrufen/Senden: {exc}", 4000),
                    "color": 0xE74C3C,
                    "timestamp": utc_now().isoformat(),
                    "footer": {"text": EMBED_FOOTER},
                }
                send_webhook(error_embed, replace_previous=False)
        except Exception as error_exc:
            print(f"Fehler-Webhook konnte nicht gesendet werden: {error_exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
