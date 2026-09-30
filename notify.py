"""Push incident alerts to ntfy with the transcript as the message body.

Configured by environment, so the topic never lands in git:

  NTFY_URL    full topic URL, e.g. https://ntfy.sh/<topic>. Unset = off.
  NTFY_TOKEN  optional access token for a protected topic or own server.
  NTFY_CLICK  page opened when the notification is tapped.

Sends run on a background thread so a slow or down ntfy server never
holds up transcription.
"""

import logging
import os
import threading
import urllib.request

log = logging.getLogger("watch_transcribe")

NTFY_URL = os.environ.get("NTFY_URL", "").strip()
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "").strip()
NTFY_CLICK = os.environ.get("NTFY_CLICK", "https://fire.scanplacer.com/").strip()
BODY_MAX = 3000  # ntfy.sh rejects message bodies over 4096 bytes

# category -> (ntfy priority 1-5, emoji tags)
STYLE = {
    "firefighter_down": (5, "sos,rotating_light"),
    "mass_casualty": (5, "rotating_light,ambulance"),
    "building_collapse": (5, "rotating_light,house"),
    "shooting": (5, "rotating_light,police_car"),
    "airport_alert": (5, "rotating_light,airplane"),
    "structure_fire": (4, "fire,house"),
    "other_fire": (4, "fire"),
    "brush_grass_fire": (4, "fire,evergreen_tree"),
    "motor_vehicle_accident": (4, "car,ambulance"),
    "technical_rescue": (4, "helmet_with_white_cross"),
    "foresthill": (3, "round_pushpin"),
}


def enabled() -> bool:
    return bool(NTFY_URL)


def _ascii(s: str) -> str:
    # HTTP headers go out as latin-1; keep titles plain.
    return (s or "").encode("ascii", "replace").decode("ascii")


def should_send(record: dict) -> bool:
    """A new alert, or an open one that a new channel has now reported."""
    return not record.get("merged_into") or bool(record.get("new_channel"))


def build(record: dict):
    """Return (title, body, headers) for one alert record."""
    label = record.get("label") or "Alert"
    channels = record.get("channels") or [record.get("talkgroup_name") or ""]
    where = " + ".join(c for c in channels if c)
    title = f"{label} - {where}" if where else label
    if record.get("merged_into"):
        title = f"{title} (now {record.get('calls') or 2} calls)"
    if record.get("place") == "foresthill" and record.get("category") != "foresthill":
        title += " - Foresthill"
    body = (record.get("text") or "").strip() or "(no transcript text)"
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX - 3] + "..."
    prio, tags = STYLE.get(record.get("category"), (4, "rotating_light"))
    headers = {
        "Title": _ascii(title),
        "Priority": str(prio),
        "Tags": tags,
    }
    if NTFY_CLICK:
        headers["Click"] = NTFY_CLICK
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    return title, body, headers


def build_confirmation(record: dict):
    """(title, body, headers) for the first follow-up confirming a dispatch."""
    conf = record.get("confirmation") or {}
    label = record.get("label") or "Alert"
    channel = conf.get("channel") or record.get("talkgroup_name") or ""
    title = f"Confirmed: {label}" + (f" - {channel}" if channel else "")
    body = (conf.get("text") or "").strip() or "(no transcript text)"
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX - 3] + "..."
    headers = {"Title": _ascii(title), "Priority": "3", "Tags": "white_check_mark"}
    if NTFY_CLICK:
        headers["Click"] = NTFY_CLICK
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    return title, body, headers


def send_confirmation(record: dict, wait: bool = False):
    """Push the confirmation that joined an alert: normal priority."""
    if not enabled() or not record.get("confirmation"):
        return
    _title, body, headers = build_confirmation(record)
    if wait:
        _post(body, headers)
        return
    threading.Thread(target=_post, args=(body, headers), daemon=True).start()


def _post(body: str, headers: dict):
    try:
        req = urllib.request.Request(NTFY_URL, data=body.encode("utf-8"),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        log.warning("ntfy push failed: %s", e)


def send(record: dict, wait: bool = False):
    """Push one alert if ntfy is configured and the record warrants it."""
    if not enabled() or not should_send(record):
        return
    _title, body, headers = build(record)
    if wait:
        _post(body, headers)
        return
    threading.Thread(target=_post, args=(body, headers), daemon=True).start()
