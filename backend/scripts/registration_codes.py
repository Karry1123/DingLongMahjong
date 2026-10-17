"""Offline registration-code administration. Plaintext codes never enter the manifest."""
import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import digest_code
from app.storage.db import connect, ensure_schema, utcnow

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generate(args):
    paths = [Path(args.out), Path(args.manifest)]
    if paths[0].resolve() == paths[1].resolve() or any(path.exists() for path in paths):
        raise ValueError('拒绝覆盖已存在的输出文件')
    if args.count < 1 or args.expires_in_days <= 0:
        raise ValueError('数量和有效天数必须为正数')
    now = utcnow()
    expires = (datetime.now(timezone.utc) + timedelta(days=args.expires_in_days)).isoformat()
    codes = set()
    while len(codes) < args.count:
        raw = ''.join(secrets.choice(ALPHABET) for _ in range(16))
        codes.add('-'.join(raw[i:i+4] for i in range(0, 16, 4)))
    codes = sorted(codes)
    manifest = {'version': 1, 'codes': [{'code_digest': digest_code(code), 'batch': args.batch, 'expires_at': expires, 'created_at': now} for code in codes]}
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    with paths[0].open('x', encoding='utf-8') as output:
        output.write('\n'.join(codes) + '\n')
    with paths[1].open('x', encoding='utf-8') as output:
        json.dump(manifest, output, ensure_ascii=False, indent=2)
    print(json.dumps({'generated': len(codes)}, ensure_ascii=False))


def import_codes(args):
    payload = json.loads(Path(args.manifest).read_text(encoding='utf-8-sig'))
    rows = payload['codes']
    for row in rows:
        if len(row['code_digest']) != 64 or any(c not in '0123456789abcdef' for c in row['code_digest']):
            raise ValueError('摘要格式错误')
        datetime.fromisoformat(row['expires_at'])
        if not row['batch']:
            raise ValueError('批次不能为空')
    if not args.dry_run:
        ensure_schema()
        with connect() as db:
            for row in rows:
                db.execute('INSERT INTO registration_codes(code_digest,batch,expires_at,created_at) VALUES(?,?,?,?) ON CONFLICT(code_digest) DO NOTHING', (row['code_digest'], row['batch'], row['expires_at'], row.get('created_at') or utcnow()))
    print(json.dumps({'codes': len(rows), 'dry_run': args.dry_run}))


def revoke(args):
    ensure_schema()
    with connect() as db:
        changed = db.execute('UPDATE registration_codes SET revoked_at=? WHERE batch=? AND used_by IS NULL AND revoked_at IS NULL', (utcnow(), args.batch))
        print(json.dumps({'revoked': changed.rowcount}))


def list_codes(args):
    ensure_schema()
    with connect() as db:
        sql = 'SELECT code_digest,batch,expires_at,used_by,used_at,revoked_at,created_at FROM registration_codes'
        rows = db.execute(sql + (' WHERE batch=?' if args.batch else '') + ' ORDER BY batch,code_digest', (args.batch,) if args.batch else ()).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('generate')
    command.add_argument('--count', type=int, required=True)
    command.add_argument('--batch', required=True)
    command.add_argument('--expires-in-days', type=int, default=30)
    command.add_argument('--out', required=True)
    command.add_argument('--manifest', required=True)
    command.set_defaults(handler=generate)
    command = sub.add_parser('import')
    command.add_argument('--manifest', required=True)
    command.add_argument('--dry-run', action='store_true')
    command.set_defaults(handler=import_codes)
    command = sub.add_parser('revoke')
    command.add_argument('--batch', required=True)
    command.set_defaults(handler=revoke)
    command = sub.add_parser('list')
    command.add_argument('--batch')
    command.set_defaults(handler=list_codes)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
