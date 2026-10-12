"""Write the paper-only PostgreSQL seed from the preserved public snapshot."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'albacore-2026-04'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def seed(source_path, output):
    raw = source_path.read_bytes()
    source = json.loads(raw)
    receipt = json.loads(source_path.with_name('public-data.json').read_text())
    checksum = hashlib.sha256(raw).hexdigest()
    if (source.get('data_kind') != 'public-wcpfc-albacore' or
            checksum != receipt['output_sha256'] or source['metadata'] != receipt['metadata']):
        raise ValueError('The seed must use the checked public snapshot.')
    metadata = literal(json.dumps(source['metadata'], ensure_ascii=False, allow_nan=False))
    lines = ['-- Apply cloud/public-data.sql first. Paper project: gvunwnpsfmylmqfqowzp.',
             '-- A version cannot be replaced with different source bytes.', 'begin;',
             'insert into public.paper_public_sources(version,source_sha256,metadata) values (' +
             ','.join((literal(VERSION), literal(checksum), metadata + '::jsonb')) +
             ') on conflict (version) do nothing;',
             'do $$ begin if not exists (select 1 from public.paper_public_sources where version=' +
             literal(VERSION) + ' and source_sha256=' + literal(checksum) +
             ' and metadata=' + metadata + '::jsonb) then raise exception ' +
             literal('Public source version already has different bytes.') + '; end if; end $$;']
    columns = ('set_id', 'source_row', 'year', 'fleet', 'quarter', 'cell', 'stratum', 'hooks', 'catch_n')
    rows = [','.join([literal(VERSION)] + [literal(row[key]) if isinstance(row[key], str)
                 else json.dumps(row[key], allow_nan=False) for key in columns]) for row in source['sets']]
    lines += ['insert into public.paper_public_sets(version,' + ','.join(columns) + ') values',
              ',\n'.join('(' + row + ')' for row in rows) + ' on conflict (version,set_id) do nothing;']
    rows = [','.join((literal(VERSION), str(row['year']), str(row['catch_t']))) for row in source['catch']]
    lines += ['insert into public.paper_public_catches(version,year,catch_t) values',
              ',\n'.join('(' + row + ')' for row in rows) + ' on conflict (version,year) do nothing;',
              'do $$ begin',
              'if (select jsonb_agg(to_jsonb(s)-' + literal('version') + ' order by source_row) from '
              'public.paper_public_sets s where version=' + literal(VERSION) + ') is distinct from ' +
              literal(json.dumps(source['sets'], ensure_ascii=False, allow_nan=False)) + '::jsonb '
              'then raise exception ' + literal('Hosted source rows differ from the checked projection.') + '; end if;',
              'if (select jsonb_agg(to_jsonb(c)-' + literal('version') + ' order by year) from '
              'public.paper_public_catches c where version=' + literal(VERSION) + ') is distinct from ' +
              literal(json.dumps(source['catch'], allow_nan=False)) + '::jsonb '
              'then raise exception ' + literal('Hosted annual catches differ from the checked projection.') + '; end if;',
              'end $$;', 'commit;']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'source_sha256': checksum, 'records': len(source['sets']),
                      'annual_catches': len(source['catch']), 'sql': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/public-source.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'cloud/public-data-seed.sql')
    args = parser.parse_args()
    seed(args.source, args.output)
