"""Download the latest 512 five-minute gold futures candles for prediction_example.py."""

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SYMBOL = "GC=F"
POINTS = 512
INTERVAL = "5m"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "GC=F_5min.csv"
CSV_COLUMNS = ["timestamps", "open", "high", "low", "close", "volume", "amount"]


def download_data() -> list[dict[str, str | float]]:
    """Fetch and validate the latest 512 five-minute gold futures candles."""
    now = datetime.now(timezone.utc)
    params = urlencode(
        {
            "period1": int((now - timedelta(days=60)).timestamp()),
            "period2": int(now.timestamp()),
            "interval": INTERVAL,
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?{params}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not download {SYMBOL} data from Yahoo Finance: {exc}") from exc

    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(f"Yahoo Finance returned an error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo Finance returned no data for {SYMBOL}.")

    result = results[0]
    quotes = result.get("indicators", {}).get("quote", [])
    if not result.get("timestamp") or not quotes:
        raise RuntimeError(f"Yahoo Finance returned no five-minute candles for {SYMBOL}.")

    quote = quotes[0]
    volumes = quote.get("volume") or []
    rows_by_timestamp = {}
    for index, timestamp in enumerate(result["timestamp"]):
        try:
            prices = {
                name: float(quote[name][index])
                for name in ("open", "high", "low", "close")
            }
            if not all(isfinite(value) for value in prices.values()):
                continue
            raw_volume = volumes[index] if index < len(volumes) else None
            volume = float(raw_volume) if raw_volume is not None else 0.0
            if not isfinite(volume):
                volume = 0.0
        except (IndexError, TypeError, ValueError):
            continue

        timestamp_text = datetime.fromtimestamp(timestamp, timezone.utc).isoformat(
            timespec="seconds"
        )
        rows_by_timestamp[timestamp_text] = {
            "timestamps": timestamp_text,
            **prices,
            "volume": volume,
            "amount": prices["close"] * volume,
        }

    rows = [rows_by_timestamp[key] for key in sorted(rows_by_timestamp)][-POINTS:]
    if len(rows) != POINTS:
        raise RuntimeError(
            f"Yahoo Finance returned only {len(rows)} valid candles; "
            f"{POINTS} are required."
        )

    # Yahoo provides OHLCV but no traded-value field; this supplies Kronos's amount column.
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"CSV destination (default: {OUTPUT_PATH})",
    )
    args = parser.parse_args()

    rows = download_data()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Saved {len(rows)} {INTERVAL} {SYMBOL} candles to {args.output} "
        f"({rows[0]['timestamps']} through {rows[-1]['timestamps']})."
    )


if __name__ == "__main__":
    main()
