from __future__ import annotations

import calendar
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://data.binance.vision/"
KLINES = {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def days(start, end):
    while start < end:
        yield start
        start += dt.timedelta(days=1)


def periods(start, end, category):
    """Monthly candles only for complete months, daily for boundary months.

    Funding has monthly archives only: retain raw source and clip normalized rows.
    Trades are daily to bound partition size and support resumable publishing.
    """
    if category == "fundingRate":
        cur = start.replace(day=1)
        while cur < end:
            yield "monthly", cur.strftime("%Y-%m")
            cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    elif category in KLINES:
        cur = start
        while cur < end:
            next_month = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
            if cur.day == 1 and next_month <= end:
                yield "monthly", cur.strftime("%Y-%m")
                cur = next_month
            else:
                yield "daily", cur.isoformat()
                cur += dt.timedelta(days=1)
    else:
        for day in days(start, end):
            yield "daily", day.isoformat()


def plan(config):
    start, end = map(dt.date.fromisoformat, [config["start"], config["end_exclusive"]])
    if start >= end:
        raise ValueError("start must precede end_exclusive")
    result = []
    for symbol in config["symbols"]:
        for category in config["categories"]:
            for period, date in periods(start, end, category):
                interval = config["interval"] if category in KLINES else None
                name = f"{symbol}-{interval or category}-{date}.zip"
                directory = f"data/{config['market']}/{period}/{category}/{symbol}/"
                if interval:
                    directory += interval + "/"
                key = directory + name
                result.append({"key": key, "url": BASE + key, "symbol": symbol,
                               "category": category, "period": period, "date": date,
                               "interval": interval, "status": "planned"})
    return result


def fetch(url, destination, timeout=60, attempts=3):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuantDataResearch/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as response, open(tmp, "wb") as out:
                headers = dict(response.headers)
                while block := response.read(1024 * 1024):
                    out.write(block)
                expected = response.headers.get("Content-Length")
            if expected is not None and tmp.stat().st_size != int(expected):
                raise ValueError("Content-Length mismatch")
            os.replace(tmp, destination)
            return headers
        except urllib.error.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            if exc.code in (403, 404, 451):
                raise
            if attempt + 1 == attempts:
                raise
            time.sleep(min(int(exc.headers.get("Retry-After", "2")), 30))
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            if "403 Forbidden" in str(exc) or "approval" in str(exc).lower():
                raise
            if attempt + 1 == attempts:
                raise
            time.sleep(1 + attempt)


def download_one(item, root):
    record = dict(item)
    target = Path(root) / "data/raw" / item["key"]
    sidecar = target.with_suffix(target.suffix + ".CHECKSUM")
    record.update({"relative_path": str(target.relative_to(root)), "attempted_at_utc": utcnow()})
    try:
        resumed = target.exists() and sidecar.exists()
        if not resumed:
            headers = fetch(item["url"] + ".CHECKSUM", sidecar)
            record["checksum_last_modified"] = headers.get("Last-Modified")
        expected = sidecar.read_text().strip().split()[0].lower()
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("Invalid source checksum")
        if not target.exists() or sha256(target) != expected:
            headers = fetch(item["url"], target)
            record["last_modified"] = headers.get("Last-Modified")
            record["etag"] = headers.get("ETag")
            record["retrieved_at_utc"] = utcnow()
        actual = sha256(target)
        if actual != expected:
            raise ValueError("SHA256 mismatch; file retained but not certified")
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            if len(names) != 1 or not names[0].endswith(".csv"):
                raise ValueError("Expected exactly one CSV member")
            # Complete SHA256 verification authenticates all ZIP bytes. Semantic QA is separate.
            record["uncompressed_bytes"] = archive.getinfo(names[0]).file_size
            record["csv_member"] = names[0]
        record.update({"status": "verified", "sha256": actual, "source_sha256": expected,
                       "bytes": target.stat().st_size, "verified_at_utc": utcnow(),
                       "resume_revalidated": resumed, "integrity_check": "full_file_sha256",
                       "semantic_validation": "pending"})
    except urllib.error.HTTPError as exc:
        record.update({"status": "source_missing" if exc.code == 404 else "access_blocked",
                       "http_status": exc.code, "error": str(exc)})
    except Exception as exc:
        record.update({"status": "access_blocked" if "403 Forbidden" in str(exc) else "error",
                       "error": f"{type(exc).__name__}: {exc}"})
    return record


def download(config, root, workers=8, categories=None, symbols=None):
    root = Path(root)
    config = dict(config)
    if categories:
        config["categories"] = categories
    if symbols:
        config["symbols"] = symbols
    jobs = plan(config)
    manifest_path = root / "manifests/acquisition.json"
    prior = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    indexed = {item["key"]: item for item in prior}
    summary = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(download_one, item, root) for item in jobs]
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            record = future.result()
            previous = indexed.get(record["key"], {})
            # Do not convert retrieval time into historical availability time on resume.
            for field in ("retrieved_at_utc", "last_modified", "etag", "checksum_last_modified"):
                if field not in record and field in previous:
                    record[field] = previous[field]
            indexed[record["key"]] = record
            summary[record["status"]] = summary.get(record["status"], 0) + 1
            if n % 20 == 0 or n == len(jobs):
                atomic_json(manifest_path, sorted(indexed.values(), key=lambda x: x["key"]))
                print(json.dumps({"completed": n, "total": len(jobs), "status": summary}), flush=True)
    return summary
