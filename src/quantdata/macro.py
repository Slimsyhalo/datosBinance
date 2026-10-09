"""Official macro context. Latest-vintage observations are NOT point-in-time data."""
import gzip
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from .acquire import atomic_json, fetch, sha256, utcnow

SERIES = {"DFF": "Effective Federal Funds Rate", "DGS2": "US Treasury 2-year yield",
          "DGS10": "US Treasury 10-year yield", "DTWEXBGS": "Broad dollar index",
          "VIXCLS": "CBOE VIX", "CPIAUCSL": "CPI US all items SA", "UNRATE": "US unemployment rate"}
CALENDARS = {"cpi": "https://www.bls.gov/schedule/news_release/cpi.htm",
             "employment": "https://www.bls.gov/schedule/news_release/empsit.htm",
             "ppi": "https://www.bls.gov/schedule/news_release/ppi.htm",
             "fomc": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"}


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.incell = [], [], "", False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th"):
            self.cell, self.incell = "", True

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.row.append(" ".join(self.cell.split()))
            self.incell = False
        if tag == "tr" and self.row:
            self.rows.append(self.row)

    def handle_data(self, data):
        if self.incell:
            self.cell += data + " "


def acquire_macro(config, root):
    root = Path(root)
    dest = root / "data/raw/macro"
    dest.mkdir(parents=True, exist_ok=True)
    normalized = root / "data/normalized/macro"
    normalized.mkdir(parents=True, exist_ok=True)
    records, events = [], []
    for code, label in SERIES.items():
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urlencode(
            {"id": code, "cosd": config["start"], "coed": str(pd.Timestamp(config["end_exclusive"]) - pd.Timedelta(days=1))[:10]})
        target = dest / f"{code}.csv"
        rec = {"series": code, "label": label, "url": url, "retrieved_at_utc": utcnow(),
               "point_in_time": False, "publication_timestamp": None, "revision_vintage": "current_at_retrieval"}
        try:
            headers = fetch(url, target)
            b = target.read_bytes()
            # Some gateways return gzip bytes without Content-Encoding metadata.
            if b.startswith(b"\x1f\x8b"):
                target.write_bytes(gzip.decompress(b))
            frame = pd.read_csv(target, na_values=["."])
            date_col = frame.columns[0]
            frame[date_col] = pd.to_datetime(frame[date_col], errors="raise")
            frame = frame[(frame[date_col] >= config["start"]) & (frame[date_col] < config["end_exclusive"])]
            frame.rename(columns={date_col: "observation_date"}).to_csv(normalized / f"{code}.csv", index=False)
            rec.update({"status": "acquired", "rows": len(frame), "sha256": sha256(target),
                        "relative_path": str(target.relative_to(root)), "last_modified": headers.get("Last-Modified")})
        except Exception as exc:
            rec.update({"status": "error", "error": str(exc)})
        records.append(rec)
    for event_type, url in CALENDARS.items():
        target = dest / f"{event_type}_calendar.html"
        rec = {"event_type": event_type, "url": url, "retrieved_at_utc": utcnow(), "point_in_time": False}
        try:
            fetch(url, target)
            b = target.read_bytes()
            if b.startswith(b"\x1f\x8b"):
                target.write_bytes(gzip.decompress(b))
            parser = Tables()
            parser.feed(target.read_text(errors="replace"))
            if event_type != "fomc":
                for row in parser.rows:
                    if len(row) < 3 or "2026" not in row[1]:
                        continue
                    try:
                        date = pd.to_datetime(row[1])
                        if not (config["start"] <= date.strftime("%Y-%m-%d") < config["end_exclusive"]):
                            continue
                        time = pd.to_datetime(row[1] + " " + row[2])
                        stamp = time.tz_localize("America/New_York").tz_convert("UTC")
                        events.append({"event_type": event_type, "reference_period": row[0],
                                       "scheduled_release_at_utc": stamp.isoformat(), "source_url": url,
                                       "actual_value": None, "consensus": None, "surprise": None,
                                       "historical_schedule_availability_verified": False})
                    except (ValueError, TypeError):
                        continue
            rec.update({"status": "acquired", "sha256": sha256(target),
                        "relative_path": str(target.relative_to(root)),
                        "schedule_rows_parsed": len(parser.rows)})
        except Exception as exc:
            rec.update({"status": "error", "error": str(exc)})
        records.append(rec)
    # FOMC calendar is stored as primary evidence; do not invent parsed announcements.
    atomic_json(root / "manifests/macro.json", records)
    atomic_json(normalized / "scheduled_events.json", sorted(events, key=lambda x: x["scheduled_release_at_utc"]))
    print(json.dumps({"macro_sources": records, "scheduled_events": len(events)}), flush=True)
