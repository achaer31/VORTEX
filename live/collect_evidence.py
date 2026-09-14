"""Private, read-only collection archives. No terminal initialization or trading."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd
import numpy as np

UTC = timezone.utc
REPO = Path(__file__).resolve().parents[1]


class CollectionError(RuntimeError):
    pass


def private_directory(state_dir):
    root = Path(state_dir).resolve()
    if root == REPO or REPO in root.parents:
        raise CollectionError("collection_must_be_outside_checkout")
    directory = root / "collection"
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve()
    if root not in directory.parents or directory == REPO or REPO in directory.parents:
        raise CollectionError("collection_directory_escape")
    return directory


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf8") as stream:
        json.dump(value, stream, allow_nan=False, separators=(",", ":")); stream.write("\n")
        stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp, path)


def append_json(path, value):
    with path.open("a", encoding="utf8") as stream:
        stream.write(json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush(); os.fsync(stream.fileno())


def archive_frames(state_dir, frames):
    """Append newly closed bars; an already archived historical bar never changes."""
    directory = private_directory(state_dir)
    columns = ["open", "high", "low", "close", "tick_volume", "spread_points", "real_volume"]
    metadata = {}
    for tf in ("M5", "M15", "H1"):
        frame = frames[tf].copy()
        if "real_volume" not in frame:
            raise CollectionError("real_volume_unavailable_for_archive")
        frame = frame[columns].apply(pd.to_numeric, errors="raise")
        if not np.isfinite(frame.to_numpy()).all() or (frame.real_volume < 0).any():
            raise CollectionError("archived_market_values_invalid")
        frame.index.name = "bar_open_utc"
        path = directory / f"XAUUSD_{tf}.csv"
        new = frame
        if path.exists():
            old = pd.read_csv(path, index_col="bar_open_utc", float_precision="round_trip")
            old.index = pd.to_datetime(old.index, utc=True, errors="raise")
            if old.empty or not old.index.is_unique or not old.index.is_monotonic_increasing:
                raise CollectionError("archived_market_data_invalid")
            overlap = frame.reindex(old.index)
            if overlap.isna().any().any() or not (overlap.to_numpy() == old[columns].to_numpy()).all():
                raise CollectionError("archived_history_changed_or_missing")
            new = frame.loc[frame.index > old.index[-1]]
        if len(new):
            with path.open("a", encoding="utf8", newline="") as stream:
                new.to_csv(stream, header=stream.tell() == 0, date_format="%Y-%m-%dT%H:%M:%SZ")
                stream.flush(); os.fsync(stream.fileno())
        metadata[tf] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "rows": len(frame), "lastBarOpenUtc": frame.index[-1].isoformat(), "appendedRows": len(new)}
    write_json(directory / "market-manifest.json", {"schemaVersion": 1, "symbol": "XAUUSD", "timeBasis": "MT5_Python_UTC", "timeframes": metadata})
    return metadata


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def collect_accounting(api, state_dir, account, now):
    """Read all deals for the current UTC day; preserve identifiers only privately.

    A day-start balance is reconstructed only for understood deal types. Equity
    drawdown cannot be reconstructed from balance transactions and stays unknown.
    """
    directory = private_directory(state_dir)
    end = datetime.fromtimestamp(now, UTC)
    begin = end.replace(hour=0, minute=0, second=0, microsecond=0)
    iso = end.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    report = {"schemaVersion": 1, "environment": "DEMO", "collectedAtUtc": iso,
              "dayStartUtc": begin.isoformat().replace("+00:00", "Z"),
              "coverage": "broker_response_for_requested_utc_day_not_independent_statement",
              "currentBalance": float(account.balance), "currentEquity": float(account.equity),
              "historyAvailable": False, "includedRegardlessOfMagic": True,
              "dayStartBalance": None, "balanceAdjustments": None, "realizedTradingPnl": None,
              "dayStartPlusBalanceAdjustments": None, "dailyEquityDrawdown": None,
              "drawdownReason": "full_intraday_equity_path_unavailable", "executionEnabled": False}
    try:
        deals = api.history_deals_get(begin, end)
        if deals is None:
            raise CollectionError("deal_history_unavailable")
        current = api.account_info()
        if (current is None or current.trade_mode != api.ACCOUNT_TRADE_MODE_DEMO or
                current.login != account.login or current.currency != "USD"):
            raise CollectionError("account_changed_during_deal_read")
        if current.balance != account.balance:
            raise CollectionError("balance_changed_during_deal_read")
        records = []
        numeric = ("ticket", "order", "time", "time_msc", "type", "entry", "magic", "position_id", "reason", "volume", "price", "commission", "swap", "profit", "fee")
        text = ("symbol", "comment", "external_id")
        for deal in deals:
            record = {k: getattr(deal, k, None) for k in (*numeric, *text)}
            if any(not finite(record[k]) for k in numeric):
                raise CollectionError("deal_history_values_unavailable")
            if any(not isinstance(record[k], str) for k in text):
                raise CollectionError("deal_history_text_unavailable")
            if not begin.timestamp() <= record["time"] <= now:
                raise CollectionError("deal_history_outside_requested_day")
            record["attribution"] = "broker_magic_zero" if record["magic"] == 0 else "broker_magic_nonzero"
            records.append(record)
        if len({r["ticket"] for r in records}) != len(records):
            raise CollectionError("deal_history_duplicate_identifiers")
        records.sort(key=lambda r: (r["time_msc"], r["ticket"]))
        journal = directory / f"deals-{begin.date().isoformat()}.jsonl"
        seen = set()
        if journal.exists():
            with journal.open(encoding="utf8") as stream:
                for line in stream:
                    seen.add(json.loads(line)["recordSha256"])
        for record in records:
            digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if digest not in seen:
                append_json(journal, {"collectedAtUtc": iso, "recordSha256": digest, "deal": record})
        report.update(historyAvailable=True, dealCount=len(records),
                      tradeDealCount=sum(r["type"] in (0, 1) for r in records),
                      historySha256=hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        # Types 0/1 are buy/sell, 2 is balance adjustment. Other accounting types
        # need explicit broker semantics; credit/commission conventions aren't guessed.
        if any(r["type"] not in (0, 1, 2) for r in records) or getattr(account, "credit", None) != 0:
            raise CollectionError("accounting_deal_type_or_credit_requires_review")
        total = sum(sum(r[k] for k in ("profit", "commission", "swap", "fee")) for r in records)
        adjustments = sum(sum(r[k] for k in ("profit", "commission", "swap", "fee")) for r in records if r["type"] == 2)
        trading = total - adjustments
        report.update(dayStartBalance=float(account.balance) - total, balanceAdjustments=adjustments,
                      realizedTradingPnl=trading, dayStartPlusBalanceAdjustments=float(account.balance) - trading,
                      reason="reconstructed_from_supported_broker_day_deals")
    except (CollectionError, OSError, ValueError, TypeError, AttributeError) as error:
        report["reason"] = str(error) if isinstance(error, CollectionError) else "private_accounting_review_required"
    write_json(directory / "accounting-latest.json", report)
    return report


def archive_account_snapshot(state_dir, payload):
    directory = private_directory(state_dir)
    # Public-schema account values only; no terminal identity or guessed starting cash.
    append_json(directory / "account-observations.jsonl", {
        "schemaVersion": 1, "producedAt": payload["producedAt"], "sessionId": payload["sessionId"],
        "sequence": payload["sequence"], "demoVerified": payload["status"]["demoVerified"],
        "account": payload["account"], "executionEnabled": False})
