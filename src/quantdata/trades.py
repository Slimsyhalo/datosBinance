"""Full-row trade audit with bounded memory, source decimals preserved in raw ZIP."""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .acquire import atomic_json, sha256, utcnow


def audit_trades(config, root):
    root = Path(root)
    records = json.loads((root / "manifests/acquisition.json").read_text())
    trades = sorted((r for r in records if r["category"] == "trades" and r["status"] == "verified"),
                    key=lambda r: (r["symbol"], r["date"]))
    existing_path = root / "reports/trades_full.json"
    previous_results = json.loads(existing_path.read_text())["partitions"] if existing_path.exists() else []
    cached = {r["key"]: r for r in previous_results}
    results, previous = [], {}
    for n, record in enumerate(trades, 1):
        result = {"key": record["key"], "symbol": record["symbol"], "date": record["date"],
                  "rows": 0, "invalid_rows": 0, "non_increasing_id_transitions": 0,
                  "regressing_time_transitions": 0, "outside_partition_rows": 0,
                  "non_consecutive_id_transitions": 0, "quote_product_mismatch_rows": 0}
        path = root / record["relative_path"]
        if cached.get(record["key"], {}).get("sha256") == record["source_sha256"] and cached[record["key"]]["status"] == "audited_all_rows":
            result = dict(cached[record["key"]])
            prior = previous.get(record["symbol"])
            if prior:
                result["id_delta_from_prior_partition"] = result["first_id"] - prior["last_id"]
                result["prior_partition_date"] = prior["date"]
            previous[record["symbol"]] = result
            results.append(result)
            continue
        start = pd.Timestamp(record["date"], tz="UTC").value // 10**6
        last_id, last_time = None, None
        try:
            if sha256(path) != record["source_sha256"]:
                raise ValueError("Source SHA256 changed")
            with zipfile.ZipFile(path) as archive, archive.open(archive.namelist()[0]) as stream:
                for frame in pd.read_csv(stream, chunksize=500_000):
                    needed = ["id", "price", "qty", "quote_qty", "time"]
                    numeric = frame[needed].apply(pd.to_numeric, errors="raise")
                    invalid = (~np.isfinite(numeric).all(axis=1) | (numeric.price <= 0)
                               | (numeric.qty <= 0) | (numeric.quote_qty <= 0)
                               | ~frame.is_buyer_maker.astype(str).str.lower().isin(["true", "false"]))
                    result["invalid_rows"] += int(invalid.sum())
                    result["outside_partition_rows"] += int(((frame.time < start) | (frame.time >= start+86_400_000)).sum())
                    id_diff, time_diff = frame.id.diff(), frame.time.diff()
                    if last_id is not None:
                        id_diff.iloc[0] = int(frame.id.iloc[0]) - last_id
                        time_diff.iloc[0] = int(frame.time.iloc[0]) - last_time
                    elif len(frame):
                        result["first_id"] = int(frame.id.iloc[0])
                        result["first_time_ms"] = int(frame.time.iloc[0])
                    result["non_increasing_id_transitions"] += int((id_diff <= 0).sum())
                    result["non_consecutive_id_transitions"] += int((id_diff > 1).sum())
                    result["regressing_time_transitions"] += int((time_diff < 0).sum())
                    expected = frame.price * frame.qty
                    tolerance = 1e-8 + expected.abs() * 1e-10
                    result["quote_product_mismatch_rows"] += int(((expected-frame.quote_qty).abs() > tolerance).sum())
                    last_id, last_time = int(frame.id.iloc[-1]), int(frame.time.iloc[-1])
                    result["rows"] += len(frame)
            result.update({"last_id": last_id, "last_time_ms": last_time, "status": "audited_all_rows",
                           "sha256": record["source_sha256"]})
            prior = previous.get(record["symbol"])
            if prior:
                result["id_delta_from_prior_partition"] = result["first_id"] - prior["last_id"]
                result["prior_partition_date"] = prior["date"]
            previous[record["symbol"]] = result
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc)})
        results.append(result)
        if n % 10 == 0 or n == len(trades):
            atomic_json(root / "reports/trades_full.json", {"generated_at_utc": utcnow(), "partitions": results,
                        "note": "ID gaps are observed transitions, not automatic proof of missing source trades"})
            print(json.dumps({"audited_partitions": n, "total_partitions": len(trades),
                              "rows": sum(r["rows"] for r in results)}), flush=True)
    atomic_json(root / "reports/trades_full.json", {"generated_at_utc": utcnow(), "partitions": results,
                "note": "ID gaps are observed transitions, not automatic proof of missing source trades"})
    return results
