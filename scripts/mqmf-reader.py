"""Add narrow-screen reading pages without changing preserved MQMF reports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = '''<style>@media(max-width:640px){
html,body{max-width:100%;overflow-wrap:anywhere}
body{box-sizing:border-box}
table,pre{display:block;max-width:100%;overflow-x:auto}
code{overflow-wrap:anywhere;word-break:break-word}
svg,img{max-width:100%;height:auto}
}</style>'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


folder = ROOT / 'docs/mqmf'
records = {}
for job in ('cpue_b', 'cpue_a', 'cpue_summary'):
    source = (folder / job / 'report.html').read_bytes()
    if source.count(b'<body>') != 1:
        raise ValueError('Expected one preserved report body: ' + job)
    page = source.replace(b'<body>', STYLE.encode() + b'<body>', 1)
    (folder / job / 'view.html').write_bytes(page)
    records[job] = {'report_sha256': sha(source), 'view_sha256': sha(page)}
(folder / 'reader-build.json').write_text(json.dumps({
    'scope': 'Narrow-screen report presentation; original reports and results unchanged',
    'style_sha256': sha(STYLE.encode()), 'files': records,
}, indent=2) + '\n')
