"""Prepare the small albacore example from the two preserved WCPFC archives."""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STRATA = ('20S_170E_Q4', '20S_175E_Q1', '20S_175E_Q2',
          '20S_175E_Q3', '20S_175E_Q4', '25S_175E_Q3')
SOURCES = (
    ('WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip',
     'd9b6904cdf2fd2f43016136992526ad355efb3c105d1796fde299cb3cec482cf',
     'WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.csv',
     '7baba3d0cf41c8577eb16588d99dacc095444e8d5f5b0acdc8b81d28d170e7c0',
     'https://www.wcpfc.int/sites/default/files/2026-04/WCPFC_L_PUBLIC_BY_YY_QTR_FLAG.zip'),
    ('WCPFC_Yearbook_Raw_Data.zip',
     'aefe9d2ee675ef11b4706dfeaaeb8ffc78c29d5bae3f6815e7f567dfc1424648',
     'XLS_SouthPacific_2026-02-25.csv',
     '99f7321beaa50bf0c152d0aafd738ca6d33f8f30959ceadba1d04629508bd19c',
     'https://www.wcpfc.int/sites/default/files/2026-03/YB_WCPFC_2026-02-25.zip'))


def read_source(folder, source):
    name, archive_hash, member, member_hash, url = source
    raw = (folder / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != archive_hash:
        raise ValueError('Source archive changed: ' + name)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        content = archive.read(member)
    if hashlib.sha256(content).hexdigest() != member_hash:
        raise ValueError('Source table changed: ' + member)
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    return rows, {'file': 'data/public/' + name, 'sha256': archive_hash,
                  'member': member, 'member_sha256': member_hash, 'url': url}


def prepare(folder, output):
    raw, longline = read_source(folder, SOURCES[0])
    totals, yearbook = read_source(folder, SOURCES[1])
    records = []
    for position, row in enumerate(raw, 1):
        year = int(row['YY'])
        if not (2000 <= year <= 2022 and row['flag_code'].strip() == 'FJ'
                and row['LAT5'].endswith('S') and int(row['LAT5'][:-1]) > 0):
            continue
        hooks = Decimal(row['HHOOKS']) * 100
        if hooks <= 0:
            continue
        count = Decimal(row['ALB_N'])
        if count < 0 or count != count.to_integral_value():
            raise ValueError('The released albacore count is not a non-negative integer.')
        cell = row['LAT5'] + '_' + row['LON5']
        quarter = int(row['QTR'])
        records.append({'set_id': 'wcpfc_ll_row_' + str(position), 'source_row': position,
                        'year': year, 'fleet': 'FJ', 'quarter': quarter, 'cell': cell,
                        'stratum': cell + '_Q' + str(quarter), 'hooks': float(hooks),
                        'catch_n': int(count)})
    annual = {year: Decimal(0) for year in range(2000, 2023)}
    catch_rows = 0
    for row in totals:
        year = int(row['YY'])
        if row['SP_CODE'] == 'ALB' and year in annual:
            annual[year] += Decimal(row['SP_MT'])
            catch_rows += 1
    if len(records) != 662 or catch_rows != 599 or any(value <= 0 for value in annual.values()):
        raise ValueError('The preserved source projection differs from its checked scope.')
    support = {(row['year'], row['stratum']) for row in records if row['stratum'] in STRATA}
    if support != {(year, stratum) for year in annual for stratum in STRATA}:
        raise ValueError('The six reference strata do not support every supplied year.')
    metadata = {
        'title': 'South Pacific albacore: a small public-data example',
        'observation_unit': 'Released fleet–quarter–5-degree-cell aggregate',
        'set_id_meaning': 'Original CSV row key; not a fishing set',
        'cpue_scope': 'Fiji fleet; six observed cell–quarter strata, 2000–2022',
        'catch_scope': 'South Pacific albacore nominal catch estimates; all gears and fleets',
        'years': [2000, 2022], 'reference_strata': list(STRATA),
        'prediction_effort_hooks': 1000, 'prediction_weights': [1 / 6] * 6,
        'normalisation': 'First supplied year = 1',
        'units': {'hooks': 'hooks; source HHOOKS multiplied by 100',
                  'catch_n': 'albacore in numbers', 'catch_t': 'metric tonnes'},
        'sources': [longline, yearbook],
        'source_terms': 'WCPFC/SPC public statistical data; retain attribution and source notices.',
        'limits': [
            'The small Fiji index is not a validated stock-wide abundance index.',
            'Blank fleet codes identify suppressed cells; their zeros are not observed catches.',
            'The released data omit vessel identities and detailed targeting information.',
            'The catch series contains nominal estimates; discards enter totals only from 2017.',
            'Recent eastern Pacific coverage is unresolved, so this example ends in 2022.',
            'Assessment and management trials use simplified teaching assumptions.']}
    source = {'sets': records, 'catch': [{'year': year, 'catch_t': float(value)}
                                        for year, value in annual.items()],
              'submission': None, 'data_kind': 'public-wcpfc-albacore', 'metadata': metadata}
    output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(source, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n'
    (output / 'public-source.json').write_bytes(encoded)
    receipt = {'schema_version': 1, 'type': 'public-source-preparation',
               'adapter': {'path': 'scripts/import-public-data.py',
                           'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
               'sources': metadata['sources'], 'source_records': len(records),
               'reference_records': len(support), 'annual_catch_source_records': catch_rows,
               'annual_catch_records': len(annual),
               'output_sha256': hashlib.sha256(encoded).hexdigest(), 'metadata': metadata}
    (output / 'public-data.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: receipt[key] for key in ('source_records', 'reference_records',
                                                 'annual_catch_records', 'output_sha256')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/public')
    parser.add_argument('--output', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    prepare(args.source, args.output)
