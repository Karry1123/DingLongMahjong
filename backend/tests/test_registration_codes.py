import json
import os
import subprocess
import sys
from pathlib import Path
from tests.test_auth import client, register

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'registration_codes.py'

def cli(*args):
    return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True,env=os.environ.copy())

def test_generate_import_register_reimport_and_revoke(client,tmp_path):
    text,manifest = tmp_path/'codes.txt',tmp_path/'manifest.json'
    args = ['generate','--count','2','--batch','test-batch','--out',text,'--manifest',manifest]
    assert cli(*args).returncode == 0
    values = text.read_text().splitlines()
    assert len(values) == 2 and all(len(value) == 19 for value in values)
    payload = manifest.read_text()
    assert all(value not in payload and value.replace('-','') not in payload for value in values)
    assert cli(*args).returncode != 0
    assert cli('import','--manifest',manifest,'--dry-run').returncode == 0
    assert register(client,registration_code=values[0]).status_code == 422
    assert cli('import','--manifest',manifest).returncode == 0
    assert register(client,registration_code=values[0]).status_code == 201
    assert cli('import','--manifest',manifest).returncode == 0
    assert register(client,account='another_user',registration_code=values[0]).status_code == 422
    assert cli('revoke','--batch','test-batch').returncode == 0
    assert cli('import','--manifest',manifest).returncode == 0
    assert register(client,account='another_user',registration_code=values[1]).status_code == 422
    rows = json.loads(cli('list','--batch','test-batch').stdout)
    assert len(rows) == 2
    assert sum(bool(row['used_by']) for row in rows) == 1
    assert sum(bool(row['revoked_at']) for row in rows) == 1
