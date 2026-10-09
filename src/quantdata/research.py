from __future__ import annotations

import datetime as dt
import json
import zipfile
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .acquire import KLINES, atomic_json, plan, sha256, utcnow

COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
           "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def write_frame(frame, path, index=True):
    """Bounded compression cost and atomic replacement prevent truncated deliverables."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    frame.to_csv(temp, index=index, compression={"method": "gzip", "compresslevel": 1, "mtime": 0})
    os.replace(temp, path)


def read_zip(path, nrows=None):
    with zipfile.ZipFile(path) as archive:
        name = archive.namelist()[0]
        with archive.open(name) as stream:
            frame = pd.read_csv(stream, nrows=nrows)
        # Older candle archives may omit headers. Never silently consume first data row.
        if str(frame.columns[0]).isdigit():
            with archive.open(name) as stream:
                frame = pd.read_csv(stream, header=None, nrows=nrows)
            if len(frame.columns) == 12:
                frame.columns = COLUMNS
            else:
                raise ValueError("Unknown headerless schema")
        return frame


def epoch_ms(series):
    values = pd.to_numeric(series, errors="raise").astype("int64")
    if values.max() > 10**14:
        # Explicit unit recognition prevents 2025+ Spot microseconds being read as ms.
        if (values % 1000 != 0).any():
            raise ValueError("Sub-millisecond timestamp cannot be represented losslessly")
        values = values // 1000
    return values


def candle_qa(frame, interval_ms=60_000, positive_prices=True):
    t = epoch_ms(frame["open_time"])
    o, h, l, c = (pd.to_numeric(frame[x], errors="raise") for x in ["open", "high", "low", "close"])
    numeric = frame[[x for x in COLUMNS if x != "ignore"]].apply(pd.to_numeric, errors="raise")
    invalid = ((h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)
               | ((l <= 0) if positive_prices else False) | (frame["volume"] < 0)
               | (frame["quote_volume"] < 0) | (frame["count"] < 0)
               | (t % interval_ms != 0) | (epoch_ms(frame["close_time"]) != t + interval_ms - 1)
               | ~np.isfinite(numeric).all(axis=1)
               | (frame["taker_buy_volume"] < 0)
               | (frame["taker_buy_volume"] > frame["volume"] + 1e-8))
    return {"rows": len(frame), "invalid_rows": int(invalid.sum()),
            "duplicate_times": int(t.duplicated().sum()),
            "out_of_order": bool((t.diff().dropna() < 0).any()),
            "observed_gap_intervals": int((t.sort_values().diff() > interval_ms).sum())}


def features(grid):
    """Features at bar close; all rolling windows reset after missing/invalid bars."""
    out = grid.copy()
    valid = out["close"].notna()
    groups = (~valid).cumsum()
    for name in ["return_1m", "atr_14", "rsi_14", "ema_20", "ema_50", "ema_200",
                 "volatility_30m", "volatility_60m", "zscore_20", "trend_20_50_bps"]:
        out[name] = np.nan
    for _, section in out[valid].groupby(groups[valid]):
        close = section["close"]
        log_returns = np.log(close).diff()
        previous = close.shift(1)
        true_range = pd.concat([section.high - section.low, (section.high - previous).abs(),
                                (section.low - previous).abs()], axis=1).max(axis=1)
        out.loc[section.index, "return_1m"] = close.pct_change(fill_method=None)
        out.loc[section.index, "atr_14"] = true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        rsi = 100 - 100 / (1 + gain / loss)
        rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
        out.loc[section.index, "rsi_14"] = rsi
        for span in (20, 50, 200):
            out.loc[section.index, f"ema_{span}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()
        for window in (30, 60):
            out.loc[section.index, f"volatility_{window}m"] = log_returns.rolling(window).std(ddof=1)
        out.loc[section.index, "zscore_20"] = (close - close.rolling(20).mean()) / close.rolling(20).std(ddof=1)
    out["trend_20_50_bps"] = (out.ema_20 / out.ema_50 - 1) * 10000
    day = out.index.floor("D")
    # Availability mask must depend only on current and earlier bars of the day.
    complete_so_far = valid.astype(int).groupby(day).cumprod().astype(bool)
    cumulative_quote = out.quote_volume.groupby(day).cumsum()
    cumulative_volume = out.volume.groupby(day).cumsum()
    out["vwap_utc_day"] = (cumulative_quote / cumulative_volume.replace(0, np.nan)).where(complete_so_far)
    out["bar_available_at_utc"] = out.index + pd.Timedelta(minutes=1)
    out["data_valid"] = valid
    return out


def audit(config, root):
    root = Path(root)
    start = pd.Timestamp(config["start"], tz="UTC")
    end = pd.Timestamp(config["end_exclusive"], tz="UTC")
    expected_index = pd.date_range(start, end, freq="1min", inclusive="left")
    records_path = root / "manifests/acquisition.json"
    records = json.loads(records_path.read_text()) if records_path.exists() else []
    requested = plan(config)
    requested_keys = {r['key'] for r in requested}
    indexed = {r["key"]: r for r in records}
    report = {"generated_at_utc": utcnow(), "window": config, "coverage": [],
              "missing_files": [r for r in requested if indexed.get(r["key"], {}).get("status") != "verified"],
              "l2_full_price_levels": "not_acquired", "trade_semantics": "first_1000_rows_per_partition_only",
              "macro_point_in_time": "not_certified", "historical_execution_fees": "not_available",
              "errors": []}
    for symbol in config["symbols"]:
        for category in config["categories"]:
            matching = [r for r in records if r["symbol"] == symbol and r["category"] == category
                        and r["status"] == "verified"
                        and (r['key'] in requested_keys or r.get('repair_for') in requested_keys)]
            frames = []
            total_rows = 0
            for record in matching:
                path = root / record["relative_path"]
                try:
                    if sha256(path) != record["source_sha256"]:
                        raise ValueError("Stored source changed since acquisition")
                    frame = read_zip(path, 1000 if category == "trades" else None)
                    if category in KLINES:
                        result = candle_qa(frame, positive_prices=category != "premiumIndexKlines")
                        if result["invalid_rows"] or result["duplicate_times"] or result["out_of_order"]:
                            raise ValueError(f"Candle semantic QA failed: {result}")
                        frame["open_time"] = epoch_ms(frame.open_time)
                        frame["close_time"] = epoch_ms(frame.close_time)
                    elif category == "trades":
                        required = {"id", "price", "qty", "quote_qty", "time", "is_buyer_maker"}
                        if not required.issubset(frame.columns):
                            raise ValueError(f"Unexpected trade schema: {list(frame.columns)}")
                        ts = epoch_ms(frame.time)
                        if ((frame.price <= 0) | (frame.qty <= 0)).any() or ts.isna().any():
                            raise ValueError("Invalid sampled trade")
                        if frame.id.duplicated().any() or (frame.id.diff().dropna() <= 0).any():
                            raise ValueError("Invalid sampled trade IDs")
                        if not frame.is_buyer_maker.astype(str).str.lower().isin(["true", "false"]).all():
                            raise ValueError("Invalid sampled maker-side flag")
                    elif category == "metrics":
                        if not {"create_time", "symbol", "sum_open_interest", "sum_open_interest_value"}.issubset(frame):
                            raise ValueError("Unexpected metrics schema")
                        if (not frame.symbol.eq(symbol).all() or (frame.sum_open_interest < 0).any()
                            or not np.isfinite(frame[["sum_open_interest", "sum_open_interest_value"]]).all().all()):
                            raise ValueError("Invalid open interest values or symbol")
                    elif category == "bookDepth":
                        if not {"timestamp", "percentage", "depth", "notional"}.issubset(frame):
                            raise ValueError("Not a recognized percentage-band depth archive")
                        if (frame[["depth", "notional"]] < 0).any().any():
                            raise ValueError("Negative aggregate depth")
                    elif category == "fundingRate":
                        if not {"calc_time", "funding_interval_hours", "last_funding_rate"}.issubset(frame):
                            raise ValueError("Unknown funding schema")
                    record["semantic_validation"] = "sampled_first_1000_rows" if category == "trades" else "full_partition"
                    record["semantically_examined_rows"] = len(frame)
                    total_rows += len(frame)
                    if category != "trades":
                        frames.append(frame)
                except Exception as exc:
                    record["semantic_validation"] = "failed"
                    report["errors"].append({"key": record["key"], "error": str(exc)})
            summary = {"symbol": symbol, "category": category,
                       "verified_files": sum(r['key'] in requested_keys for r in matching),
                       "supplemental_files": sum(r['key'] not in requested_keys for r in matching),
                       "expected_files": sum(r["symbol"] == symbol and r["category"] == category for r in requested),
                       "rows_examined": total_rows}
            if category in KLINES:
                frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
                frame.index = pd.to_datetime(frame.open_time, unit="ms", utc=True)
                frame = frame[(frame.index >= start) & (frame.index < end)].sort_index()
                if frame.index.duplicated().any():
                    raise ValueError(f"Cross-file duplicate candles: {symbol}/{category}")
                grid = frame.reindex(expected_index)
                grid.index.name = "open_time_utc"
                summary.update({"expected_rows": len(expected_index), "observed_rows": len(frame),
                                "missing_rows": int(grid.close.isna().sum()),
                                "coverage_fraction": len(frame) / len(expected_index)})
                dest = root / f"data/normalized/{symbol}/{category}"
                dest.mkdir(parents=True, exist_ok=True)
                write_frame(grid, dest / "1m.csv.gz")
                if category == "klines":
                    feats = features(grid)
                    fdir = root / f"data/features/{symbol}"
                    fdir.mkdir(parents=True, exist_ok=True)
                    write_frame(feats, fdir / "1m.csv.gz")
                    for rule, count in (("5min", 5), ("15min", 15), ("1h", 60)):
                        aggregates = grid.resample(rule, label="left", closed="left").agg(
                            {"open": "first", "high": "max", "low": "min", "close": "last",
                             "volume": "sum", "quote_volume": "sum", "count": "sum",
                             "taker_buy_volume": "sum", "taker_buy_quote_volume": "sum"})
                        aggregates = aggregates[grid.close.resample(rule).count().eq(count)]
                        aggregates["bar_available_at_utc"] = aggregates.index + pd.Timedelta(rule)
                        write_frame(aggregates, dest / f"{rule}.csv.gz")
            elif frames:
                frame = pd.concat(frames, ignore_index=True)
                col = {"metrics": "create_time", "bookDepth": "timestamp", "fundingRate": "calc_time"}[category]
                times = pd.to_datetime(epoch_ms(frame[col]), unit="ms", utc=True) if category == "fundingRate" else pd.to_datetime(frame[col], utc=True)
                frame["event_time_utc"] = times
                frame = frame[(times >= start) & (times < end)].sort_values("event_time_utc")
                subset = ["event_time_utc", "percentage"] if category == "bookDepth" else ["event_time_utc"]
                summary["duplicate_rows"] = int(frame.duplicated(subset=subset).sum())
                summary["observed_rows"] = len(frame)
                if category == "metrics":
                    expected = pd.date_range(start, end, freq="5min", inclusive="left")
                    observed = pd.DatetimeIndex(frame.event_time_utc)
                    summary["expected_5m_timestamps"] = len(expected)
                    summary["missing_5m_timestamps"] = len(expected.difference(observed))
                    summary["off_5m_grid_timestamps"] = len(observed.difference(expected))
                dest = root / f"data/normalized/{symbol}"
                dest.mkdir(parents=True, exist_ok=True)
                write_frame(frame, dest / f"{category}.csv.gz", index=False)
            report["coverage"].append(summary)
    # Preserve records from an independent acquisition campaign completed during QA.
    latest_records = json.loads(records_path.read_text()) if records_path.exists() else []
    merged = {r["key"]: r for r in latest_records}
    merged.update({r["key"]: r for r in records})
    atomic_json(records_path, sorted(merged.values(), key=lambda r: r["key"]))
    atomic_json(root / "reports/quality.json", report)
    rows = ["# Informe de cobertura real", "", f"Generado: {report['generated_at_utc']}", "",
            f"Ventana UTC: {config['start']} inclusive → {config['end_exclusive']} exclusive.", "",
            "| Activo | Categoría | Archivos verificados / previstos | Filas observadas o examinadas | Faltantes 1m |",
            "|---|---|---:|---:|---:|"]
    for r in report["coverage"]:
        rows.append(f"| {r['symbol']} | {r['category']} | {r['verified_files']}/{r['expected_files']} | {r.get('observed_rows',r['rows_examined'])} | {r.get('missing_rows','—')} |")
    rows.extend(["", f"Errores semánticos: {len(report['errors'])}. Archivos ausentes/no adquiridos: {len(report['missing_files'])}.",
                 "", "Trades: checksum de todos los bytes; este reporte examina las primeras 1.000 filas por partición. La auditoría completa, cuando se ejecuta, está en trades_full.json. No confundir filas de prechequeo con total de operaciones.",
                 "", "L2 completo histórico: no adquirido. bookDepth es profundidad agregada por bandas porcentuales.",
                 "", "Open interest: faltantes de timestamps de 5 minutos en quality.json; no se interpolan.",
                 "", "Macros FRED: valores revisados actuales, sin certificación point-in-time; no utilizarlos como si fueran conocidos históricamente.",
                 "", "Comisiones/slippage: escenarios supuestos; tarifas reales de la cuenta y costos históricos no certificados."])
    (root / "reports/QUALITY.md").write_text("\n".join(rows) + "\n")
    print(json.dumps({"coverage": report["coverage"], "errors": len(report["errors"])}), flush=True)
