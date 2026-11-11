"""Read pages from the Journal Notion database."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from notion_client import Client, NotionClientError


DEFAULT_DATABASE_URL = "NOTION_DATABASE_URL_OR_ID"
DEFAULT_API_VERSION = "2026-03-11"


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def notion_id(value: str) -> str:
    """Extract a UUID-like Notion ID from a URL or accept an ID directly."""
    match = re.search(r"([0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", value, re.I)
    if not match:
        raise ValueError(f"Could not find a Notion ID in: {value}")
    raw = match.group(1).replace("-", "").lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def all_pages(client: Client, data_source_id: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        payload: dict[str, Any] = {"data_source_id": data_source_id, "page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        result = client.data_sources.query(**payload)
        pages.extend(result.get("results", []))
        if not result.get("has_more"):
            return pages
        cursor = result.get("next_cursor")
        if not cursor:
            raise RuntimeError("Notion indicated more results but returned no next_cursor")


def get_data_source_id(client: Client, database_id: str) -> str:
    database = client.databases.retrieve(database_id=database_id)
    sources = database.get("data_sources") or []
    if sources:
        return sources[0]["id"]
    raise RuntimeError("No data source found; check database access and the supplied URL.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE_URL, help="Notion database URL or ID")
    parser.add_argument("--page-id", help="Retrieve one page instead of listing database pages")
    parser.add_argument("--output", type=Path, help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    load_env_file(Path(__file__).with_name(".env.local"))
    token = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_API_TOKEN")
    if not token:
        print("Missing NOTION_API_KEY in .env.local or the environment.", file=sys.stderr)
        return 2
    try:
        client = Client(auth=token, notion_version=os.getenv("NOTION_API_VERSION", DEFAULT_API_VERSION))
        database_id = notion_id(args.database)
        result: Any = client.pages.retrieve(page_id=notion_id(args.page_id)) if args.page_id else all_pages(
            client, get_data_source_id(client, database_id)
        )
    except (NotionClientError, RuntimeError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(output + "\n")
        print(f"Wrote {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
