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
        raise RuntimeError(
            "Discord hat keine Nachrichten-ID zurückgegeben."
        ) from exc

    # Die Workflow-Datei muss diese Datei anschließend ins Repository committen.
    # So steht die ID beim nächsten täglichen GitHub-Actions-Lauf wieder bereit.
    with open(message_id_file, "w", encoding="utf-8") as file:
        file.write(new_message_id)

    print(f"Discord-Nachricht gesendet. ID: {new_message_id}")


# =========================
# Main
# =========================

def main() -> int:

    try:

        today = utc_now().strftime(
            "%Y-%m-%d"
        )

        data = fetch_json(
            EVENT_INDEX_URL
        )

        (
            week,
            target_day,
            mission_rows,
            vendor_rows,
        ) = pick_escalation_snapshot(
            data,
            today,
        )

        embed = build_discord_embed(
            week,
            target_day,
            mission_rows,
            vendor_rows,
        )

        send_webhook(embed)

        print(
            "Webhook sent successfully."
        )

        return 0

    except Exception as exc:

        print(
            f"Job failed: {exc}",
            file=sys.stderr,
        )

        try:

            if DISCORD_WEBHOOK_URL:

                error_embed = {
                    "title": (
                        "Division 2 Daily Reset - Fehler"
                    ),

                    "description": truncate(
                        f"Fehler beim Abrufen/Senden: {exc}",
                        4000,
                    ),

                    "color": 0xE74C3C,

                    "timestamp": utc_now().isoformat(),

                    "footer": {
                        "text": EMBED_FOOTER,
                    },
                }

                send_webhook(
                    error_embed,
                    replace_previous=False,
                )

        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
