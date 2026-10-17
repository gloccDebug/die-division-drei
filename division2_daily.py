    )


def build_discord_embed(week, target_day, mission_rows, vendor_rows) -> Dict[str, Any]:
    fields = []
    if mission_rows:
        fields.append({
            "name": "Missions / Target Loot",
            "value": truncate("\\n".join(
                f"**{name}**" + (f" — {detail}" if detail else "")
                for name, detail in mission_rows
            ), 1024),
            "inline": False,
        })
    if vendor_rows:
        fields.append({
            "name": "Vendors",
            "value": truncate("\\n".join(
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
