"""USD-M L2 snapshot+diff capture. Resync on pu gaps; never synthesize history."""
import asyncio
import gzip
import json
import time
import urllib.request
from decimal import Decimal
from pathlib import Path

import websockets

from .acquire import atomic_json, utcnow


class Book:
    def __init__(self, snapshot):
        self.last = int(snapshot["lastUpdateId"])
        self.bids = {Decimal(p): Decimal(q) for p, q in snapshot["bids"]}
        self.asks = {Decimal(p): Decimal(q) for p, q in snapshot["asks"]}
        self.started = False

    def apply(self, event):
        if event["u"] < self.last:
            return False
        if not self.started:
            if not event["U"] <= self.last <= event["u"]:
                raise ValueError("Snapshot does not bridge first diff")
        elif event["pu"] != self.last:
            raise ValueError("L2 sequence gap; new snapshot required")
        for name, field in (("bids", "b"), ("asks", "a")):
            side = getattr(self, name)
            for price, qty in event[field]:
                p, q = Decimal(price), Decimal(qty)
                if q == 0:
                    side.pop(p, None)
                else:
                    side[p] = q
        self.last, self.started = event["u"], True
        if self.bids and self.asks and max(self.bids) >= min(self.asks):
            raise ValueError("Crossed book after diff")
        return True


def snapshot(symbol):
    with urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=1000", timeout=20) as r:
        return json.load(r)


async def capture_symbol(root, symbol, seconds):
    destination = Path(root) / "data/live" / symbol
    destination.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "-")
    path = destination / f"l2-{stamp}.jsonl.gz"
    report = {"symbol": symbol, "started_at_utc": utcnow(), "status": "capturing",
              "historical_backfill": False, "snapshot_levels": 1000, "events": 0,
              "synchronized_events": 0, "sessions": 0, "gaps": 0}
    stop = time.monotonic() + seconds
    # Current documented base route; configurable by code when Binance changes streams.
    url = f"wss://fstream.binance.com/public/ws/{symbol.lower()}@depth@100ms"
    try:
        with gzip.open(path, "wt") as out:
            while time.monotonic() < stop:
                async with websockets.connect(url, open_timeout=20) as ws:
                    report["sessions"] += 1
                    task = asyncio.create_task(asyncio.to_thread(snapshot, symbol))
                    buffered = []
                    try:
                        while not task.done():
                            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=min(5, max(.1, stop-time.monotonic()))))
                            envelope = {"type": "diff", "received_at_utc": utcnow(), "session": report["sessions"], "payload": event}
                            buffered.append(envelope)
                            out.write(json.dumps(envelope) + "\n")
                            report["events"] += 1
                            if len(buffered) > 20000:
                                raise ValueError("Snapshot too slow; buffer exceeded")
                        snap = await task
                    finally:
                        if not task.done():
                            task.cancel()
                    out.write(json.dumps({"type": "snapshot", "received_at_utc": utcnow(),
                                          "session": report["sessions"], "payload": snap}) + "\n")
                    book = Book(snap)
                    try:
                        for envelope in buffered:
                            report["synchronized_events"] += int(book.apply(envelope["payload"]))
                        while time.monotonic() < stop:
                            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(.1, stop-time.monotonic())))
                            report["events"] += 1
                            out.write(json.dumps({"type": "diff", "received_at_utc": utcnow(),
                                                  "session": report["sessions"], "payload": event}) + "\n")
                            report["synchronized_events"] += int(book.apply(event))
                    except ValueError as exc:
                        report["gaps"] += 1
                        out.write(json.dumps({"type": "gap", "received_at_utc": utcnow(), "error": str(exc)}) + "\n")
                        continue
                    except asyncio.TimeoutError:
                        break
        report["status"] = "captured" if report["synchronized_events"] else "no_synchronized_data"
    except Exception as exc:
        report.update({"status": "blocked_or_failed", "error": str(exc)})
    report["ended_at_utc"] = utcnow()
    atomic_json(destination / f"l2-{stamp}-status.json", report)
    return report


async def capture(root, symbols, seconds):
    print(json.dumps(await asyncio.gather(*(capture_symbol(root, s, seconds) for s in symbols))), flush=True)
