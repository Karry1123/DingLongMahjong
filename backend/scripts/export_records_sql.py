"""Export selected local PvE archives as an idempotent PostgreSQL import script.

No connection credentials are read. SQLite sources are opened read-only.
"""

import argparse
import json
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path


def sql_text(value):
    return "'" + str(value).replace("'", "''") + "'"


def export_records(sqlite_path=None, json_dir=None):
    records = {}
    if sqlite_path:
        path = Path(sqlite_path).resolve()
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            for game_id, round_id, timestamp, payload in db.execute(
                "SELECT game_id,round_id,timestamp,payload FROM game_records ORDER BY id"
            ):
                records[game_id] = (round_id, timestamp, bytes(payload))
    if json_dir:
        for path in sorted(Path(json_dir).glob("GM-*.json")):
            record = json.loads(path.read_text(encoding="utf-8-sig"))
            game_id, round_id, timestamp = (
                record[key] for key in ("game_id", "round_id", "timestamp")
            )
            payload = zlib.compress(json.dumps(record, ensure_ascii=False).encode("utf-8"), 6)
            if game_id in records and records[game_id][:2] != (round_id, timestamp):
                raise ValueError("Conflicting game identity")
            records[game_id] = (round_id, timestamp, payload)
    lines = ["BEGIN;", "SET LOCAL standard_conforming_strings = on;",
             "CREATE TABLE IF NOT EXISTS game_records (id BIGSERIAL PRIMARY KEY, "
             "game_id TEXT NOT NULL UNIQUE, round_id TEXT NOT NULL UNIQUE, "
             "timestamp TEXT NOT NULL, payload BYTEA NOT NULL);",
             "LOCK TABLE game_records IN EXCLUSIVE MODE;"]
    for game_id, (round_id, timestamp, payload) in records.items():
        # Preserve identifiers, timestamps and compressed replay payloads.
        lines.append("INSERT INTO game_records(game_id,round_id,timestamp,payload) VALUES ("
                     + ",".join(map(sql_text, (game_id, round_id, timestamp)))
                     + ",decode('" + payload.hex() + "','hex')) ON CONFLICT DO NOTHING;")
    lines.extend(["COMMIT;", "SELECT COUNT(*) AS imported_total FROM game_records;"])
    return "\n".join(lines) + "\n", len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path)
    parser.add_argument("--json-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.sqlite and not args.json_dir:
        parser.error("Provide --sqlite and/or --json-dir")
    sql, count = export_records(args.sqlite, args.json_dir)
    args.output.write_text(sql, encoding="utf-8")
    print(f"Exported {count} records to {args.output}")


if __name__ == "__main__":
    main()
