import json
import sqlite3
import zlib

from app.core.record_manager import archive_completed_game
from scripts.export_records_sql import export_records
from tests.test_game_records import completed


def test_export_preserves_identity_and_replay_without_changing_source(tmp_path):
    path = tmp_path / "source.sqlite3"
    meta = archive_completed_game(completed("round'quoted"), db_path=path)
    with sqlite3.connect(path) as db:
        saved = db.execute("SELECT payload FROM game_records").fetchone()[0]
    output, count = export_records(sqlite_path=path)
    assert count == 1
    assert meta['game_id'] in output and meta['timestamp'] in output
    assert "round''quoted" in output and saved.hex() in output
    assert "ON CONFLICT DO NOTHING" in output and "DELETE" not in output
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT payload FROM game_records").fetchone()[0] == saved
    record = json.loads(zlib.decompress(saved))
    (tmp_path / (meta['game_id'] + '.json')).write_text(json.dumps(record), encoding='utf-8-sig')
    output, count = export_records(json_dir=tmp_path)
    assert count == 1 and meta['timestamp'] in output
