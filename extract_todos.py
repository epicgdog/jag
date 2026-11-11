"""Extract checkbox to-dos from a Notion page, including nested blocks."""

import argparse
import json
import os
import sys
from pathlib import Path

from notion_client import Client, NotionClientError
from notion_client.helpers import iterate_paginated_api

from main import DEFAULT_API_VERSION, load_env_file, notion_id


def extract_todos(client: Client, block_id: str) -> list[dict]:
    todos = []
    for block in iterate_paginated_api(
        client.blocks.children.list, block_id=block_id, page_size=100
    ):
        if block["type"] == "to_do":
            todo = block["to_do"]
            todos.append({
                "id": block["id"],
                "text": "".join(part.get("plain_text", "") for part in todo["rich_text"]),
                "checked": todo["checked"],
            })
        # Stay within this document rather than entering separate pages/databases.
        if block.get("has_children") and block["type"] not in {"child_page", "child_database"}:
            todos.extend(extract_todos(client, block["id"]))
    return todos


def todos_from_snapshot(blocks: list[dict]) -> list[dict]:
    """Extract tasks from a previously traversed, ordered block snapshot."""
    return [
        {"id": block["id"], "text": "".join(part.get("plain_text", "") for part in block["to_do"]["rich_text"]), "checked": block["to_do"]["checked"]}
        for block in blocks if block.get("type") == "to_do"
    ]

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", help="Notion page URL or ID")
    parser.add_argument("--unchecked", action="store_true", help="Only return unfinished to-dos")
    args = parser.parse_args()

    load_env_file(Path(__file__).with_name(".env.local"))
    token = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_API_TOKEN")
    if not token:
        print("Missing NOTION_API_KEY in .env.local or the environment.", file=sys.stderr)
        return 2

    try:
        with Client(
            auth=token, notion_version=os.getenv("NOTION_API_VERSION", DEFAULT_API_VERSION)
        ) as client:
            todos = extract_todos(client, notion_id(args.page))
    except (NotionClientError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.unchecked:
        todos = [todo for todo in todos if not todo["checked"]]
    print(json.dumps(todos, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
