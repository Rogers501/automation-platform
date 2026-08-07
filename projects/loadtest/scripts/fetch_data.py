"""Fetch waybill data from the data source API and write to CSV.

Queries the production waybill database via paginated API, extracts fields
needed by the cost-calculation load test, and writes them to a CSV file.
The CSV is consumed by DataProvider templates ({{csv.cost_data.<col>}}) in
the load test scenario YAML.

Usage (run from projects/loadtest/ directory)::

    # Inspect response structure first (recommended)
    python scripts/fetch_data.py --inspect

    # Fetch 1000 pages x 1000 records = 1,000,000 records
    python scripts/fetch_data.py

    # Custom page count and output path
    python scripts/fetch_data.py --pages 500 --output data/custom.csv

Requires httpx (available via framework dependency). Use the main .venv
or the loadtest venv (both have httpx through framework).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Data source API configuration
# ---------------------------------------------------------------------------
DATA_SOURCE_URL = "http://10.94.7.105:30122/waybillouterapi/order/waybillTimeRangePage"
AUTH_TOKEN = "17f718ef5e0d4f108a66cc57c239dd01"
START_TIME = "2026-06-01 00:00:00"
END_TIME = "2026-07-01 00:00:00"
PAGE_SIZE = 1000

# Concurrency: 20 concurrent page requests (balance speed vs. source API load).
MAX_CONCURRENT = 20
REQUEST_TIMEOUT = 30  # seconds per page request
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# CSV output columns -- must match {{csv.cost_data.<col>}} in scenario YAML
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "waybillId",
    "startPointNetworkCode",
    "terminalPostalCode",
    "productTypeId",
    "productTypeCode",
    "goodsTypeId",
    "goodsTypeCode",
    "number",
    "currentTime",
    "insuredAmount",
    "startNetworkCode",
]

# Field name aliases: try these keys in the record if the primary name is absent.
# Ordered by likelihood (camelCase first, then snake_case, then alternatives).
FIELD_ALIASES: dict[str, list[str]] = {
    "waybillId": ["waybillId", "waybill_id", "id", "waybillNo"],
    "startPointNetworkCode": [
        "startPointNetworkCode",
        "start_point_network_code",
        "startNetworkCode",
        "start_network_code",
    ],
    "terminalPostalCode": [
        "terminalPostalCode",
        "terminal_postal_code",
        "receiverPostalCode",
        "destPostalCode",
        "destPostalCode",
    ],
    "productTypeId": ["productTypeId", "product_type_id"],
    "productTypeCode": ["productTypeCode", "product_type_code"],
    "goodsTypeId": ["goodsTypeId", "goods_type_id"],
    "goodsTypeCode": ["goodsTypeCode", "goods_type_code"],
    "number": ["number", "weight", "chargeWeight", "charge_weight", "calcWeight"],
    "currentTime": [
        "currentTime",
        "current_time",
        "createTime",
        "create_time",
        "inputTime",
        "orderTime",
    ],
    "insuredAmount": [
        "insuredAmount",
        "insured_amount",
        "insuranceValue",
        "insurance_value",
    ],
    "startNetworkCode": [
        "startNetworkCode",
        "start_network_code",
        "startPointNetworkCode",
        "start_point_network_code",
    ],
}

# Default values for fields that might be missing in the data source.
DEFAULTS: dict[str, str] = {
    "productTypeId": "100",
    "productTypeCode": "EZ",
    "goodsTypeId": "60",
    "goodsTypeCode": "bm000006",
    "number": "0.5",
    "insuredAmount": "0.69",
}


def extract_fields(record: dict[str, Any]) -> dict[str, str]:
    """Extract CSV columns from a data source record using alias fallback."""
    row: dict[str, str] = {}
    for col in CSV_COLUMNS:
        value: str | None = None
        for alias in FIELD_ALIASES.get(col, [col]):
            if alias in record and record[alias] is not None:
                value = str(record[alias])
                break
        if value is None:
            value = DEFAULTS.get(col, "")
        row[col] = value
    return row


def find_records(data: Any) -> list[dict[str, Any]]:
    """Find the records list in common API response structures."""
    if isinstance(data, dict):
        # MyBatis-Plus IPage: {"data": {"records": [...]}}
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("records"), list):
            return inner["records"]
        # Direct list: {"data": [...]}
        if isinstance(inner, list):
            return inner
        # Top-level records: {"records": [...]}
        if isinstance(data.get("records"), list):
            return data["records"]
    if isinstance(data, list):
        return data
    return []


async def fetch_page(
    client: httpx.AsyncClient,
    page_num: int,
    semaphore: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    """Fetch a single page with retry logic."""
    body = {
        "pageSize": PAGE_SIZE,
        "current": page_num,
        "startTime": START_TIME,
        "endTime": END_TIME,
    }
    headers = {
        "authtoken": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(
                    DATA_SOURCE_URL,
                    json=body,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                return find_records(resp.json())
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    print(
                        f"  [ERROR] page {page_num} failed after {MAX_RETRIES} retries: {exc}",
                        file=sys.stderr,
                    )
                    return []
                await asyncio.sleep(1.0 * (attempt + 1))
    return []


async def inspect_mode() -> None:
    """Fetch first page and print response structure for field mapping verification."""
    print(f"URL: {DATA_SOURCE_URL}")
    print(f"Body: pageSize={PAGE_SIZE}, current=1, startTime={START_TIME}, endTime={END_TIME}")
    print()

    async with httpx.AsyncClient() as client:
        records = await fetch_page(client, 1, asyncio.Semaphore(1))

    if not records:
        print("[ERROR] No records returned. Check API URL, token, and time range.")
        return

    print(f"Records on page 1: {len(records)}")
    print(f"Fields in first record ({len(records[0])} keys):")
    for key in records[0]:
        val = records[0][key]
        val_str = str(val)
        if len(val_str) > 60:
            val_str = val_str[:60] + "..."
        print(f"  {key}: {val_str} ({type(val).__name__})")

    print("\n--- Field mapping preview ---")
    sample_row = extract_fields(records[0])
    for col in CSV_COLUMNS:
        print(f"  {col} -> {sample_row[col]}")


async def fetch_all(pages: int, output: Path) -> None:
    """Fetch all pages concurrently and write to CSV."""
    output.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    print(f"Target: {pages} pages x {PAGE_SIZE} = {pages * PAGE_SIZE} records")
    print(f"Output: {output}")
    print(f"Concurrency: {MAX_CONCURRENT}")
    print()

    # Write CSV header.
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

    total = 0
    async with httpx.AsyncClient() as client:
        # Fetch first page separately to verify and show structure.
        print("Fetching page 1 (structure verification)...")
        first_records = await fetch_page(client, 1, semaphore)
        if not first_records:
            print("[ERROR] No records on page 1. Run with --inspect to debug.")
            return

        print(f"  Record count: {len(first_records)}")
        print(f"  First record keys: {list(first_records[0].keys())}")

        with output.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            for rec in first_records:
                writer.writerow(extract_fields(rec))
        total += len(first_records)
        print(f"  Written: {total} records")

        if pages <= 1:
            print(f"\nDone! {total} records written to {output}")
            return

        # Fetch remaining pages in batches.
        batch_size = MAX_CONCURRENT * 2
        print(f"\nFetching pages 2-{pages} in batches of {batch_size}...")

        for batch_start in range(2, pages + 1, batch_size):
            batch_end = min(batch_start + batch_size, pages + 1)
            tasks = [fetch_page(client, p, semaphore) for p in range(batch_start, batch_end)]
            results = await asyncio.gather(*tasks)

            with output.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                for records in results:
                    for rec in records:
                        writer.writerow(extract_fields(rec))
                    total += len(records)

            print(f"  Pages {batch_start}-{batch_end - 1}: {total} records total")

    print(f"\nDone! {total} records written to {output}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch waybill data from data source API -> CSV for load testing"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Fetch first page only and print response structure, then exit",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1000,
        help="Number of pages to fetch (default: 1000 = 1,000,000 records)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/cost_data.csv",
        help="Output CSV file path (default: data/cost_data.csv)",
    )
    args = parser.parse_args()

    if args.inspect:
        asyncio.run(inspect_mode())
    else:
        asyncio.run(fetch_all(args.pages, Path(args.output)))


if __name__ == "__main__":
    main()
