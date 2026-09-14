"""Optional owner-enabled Telegram notification queue; no automatic messaging.

Only changes in bounded monitoring state are queued. Quotes, balances, IDs,
credentials and arbitrary journal prose are never included in message text.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, build_opener

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from live.publish_telemetry import NoRedirect, PublisherStop, load_snapshot


def meaningful_state(s):
    status = s["status"]
    v = s.get("v02", {})
    protection = v.get("protection", {})
    state = {"demoVerified": status["demoVerified"], "connected": status["terminalConnected"],
             "fresh": protection.get("dataFresh", False), "kill": protection.get("killSwitch", True),
             "mode": v.get("mode", "FROZEN")}
    if state["mode"] not in ("NORMAL", "AGGRESSIVE", "EXTREME", "FROZEN", "KILL"):
        raise PublisherStop("notification_state_invalid")
    return state


def queue_change(directory, snapshot):
    directory = Path(directory).resolve()
    if directory == REPO or REPO in directory.parents:
        raise PublisherStop("notification_state_must_be_private")
    path = directory / "telegram-state.json"
    state = json.loads(path.read_text()) if path.exists() else {"last": None, "pending": [], "uncertain": False}
    current = meaningful_state(snapshot)
    if current == state["last"]:
        return False
    text = "VORTEX demo observer: " + ", ".join(f"{k}={v}" for k, v in current.items()) + ". No execution enabled."
    state["pending"] = (state["pending"] + [{"id": hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest(), "text": text}])[-50:]
    state["last"] = current
    _save(path, state)
    return True


def _save(path, value):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as stream:
        json.dump(value, stream, separators=(",", ":")); stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp, path)


def send_pending(directory, env, opener=None):
    directory = Path(directory).resolve()
    if directory == REPO or REPO in directory.parents:
        raise PublisherStop("notification_state_must_be_private")
    if env.get("VORTEX_TELEGRAM_ENABLE") != "user_enabled":
        raise PublisherStop("telegram_explicit_owner_enable_required")
    token = env.get("VORTEX_TELEGRAM_BOT_TOKEN", ""); chat = env.get("VORTEX_TELEGRAM_CHAT_ID", "")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token) or not re.fullmatch(r"-?[0-9]+", chat):
        raise PublisherStop("private_telegram_configuration_required")
    path = Path(directory) / "telegram-state.json"
    state = json.loads(path.read_text())
    if state["uncertain"]:
        raise PublisherStop("telegram_uncertain_delivery_needs_review")
    if not state["pending"]:
        return "empty"
    item = state["pending"][0]
    # Persist uncertainty BEFORE transmission: Telegram has no idempotency key.
    state["uncertain"] = True; _save(path, state)
    body = json.dumps({"chat_id": chat, "text": item["text"], "disable_notification": True}).encode()
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=10) as response:
            accepted = response.status == 200 and json.loads(response.read(16384)).get("ok") is True
    except Exception:
        return "delivery_uncertain"
    if not accepted:
        return "delivery_uncertain"
    state["pending"].pop(0); state["uncertain"] = False; _save(path, state)
    return "sent"


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="requires explicit owner enable and private bot/chat settings")
    parser.add_argument("--queue", action="store_true", help="queue a meaningful change locally; sends nothing")
    args = parser.parse_args(argv); env = os.environ if env is None else env
    try:
        directory = Path(env["VORTEX_STATE_DIR"]).resolve()
        if directory == REPO or REPO in directory.parents:
            raise PublisherStop("notification_state_must_be_private")
        if not args.queue and not args.send:
            print("Telegram helper inactive; no queue or messages created."); return 0
        snapshot = json.loads(load_snapshot(directory / "status.json", time.time()))
        queue_change(directory, snapshot)
        if args.send:
            print("Telegram: " + send_pending(directory, env))
        else:
            print("Telegram change checked and queued locally; no message sent.")
        return 0
    except (PublisherStop, KeyError, OSError, ValueError):
        print("Telegram helper inactive: private_configuration_or_state_review_required", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
