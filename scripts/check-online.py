"""Optional integration check: run the online demo without a reader login."""
import json,time,urllib.request,urllib.error
from pathlib import Path
BASE='https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api'
ROOT=Path(__file__).resolve().parents[1]

def request(path,body=None,session=None):
 headers={'Content-Type':'application/json'}
 if session:
  path+=('&' if '?' in path else '?')+'session='+session['id'];headers['Authorization']='Bearer '+session['token']
 r=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(r,timeout=40) as response:return json.load(response)
 except urllib.error.HTTPError as e:raise RuntimeError(str(e.code)+' '+json.load(e).get('error','Request failed'))

(ROOT/'.state').mkdir(exist_ok=True)
session=request('/session',{})
p=ROOT/'.state/test-reader.json';p.write_text(json.dumps(session));p.chmod(0o600)
settings={'last_year':2023,'min_hooks_a':0,'mortality_2':.3}
checks=[]

def execute(start,handover='connected',previous=None):
 result=request('/run',{'start':start,'settings':settings,'handover':handover},session)
 print('Requested',start,result['id'],flush=True)
 cursor=0;deadline=time.monotonic()+600;transferred=False
 while time.monotonic()<deadline:
  update=request('/state?after='+str(cursor),session=session)
  for row in update['events']:
   cursor=row['id'];e=row['event'];print(e.get('job','workflow'),e['state'],e.get('title',''),flush=True)
   if e['state']=='handover':
    assert previous and update['state']['records']['assessment_a1']['run_id']==previous['records']['assessment_a1']['run_id']
    assert update['state']['records']['cpue_a']['run_id']!=previous['records']['cpue_a']['run_id']
    old=request('/output?job=assessment_a1',session=session)
    assert old['record']==previous['records']['assessment_a1']
    request('/transfer',{'connect':False},session);transferred=True
  run=update['run']
  if run and run['status'] in ('failed','expired'):raise RuntimeError(run.get('error') or run['status'])
  if run and run['status']=='complete':
   value=run['result'];checks.append({'start':start,'handover':handover,'github_run':run['github_run'],'commit':run['commit_sha'],'executed':value['run'],'retained':value['retained'],'manual_transfer_checked':transferred})
   print('Completed GitHub run',run['github_run'],'jobs',len(value['run']),flush=True)
   return value
  time.sleep(1)
 raise TimeoutError('Online execution timed out')

full=execute('submission');assert len(full['run'])==16
partial=execute('cpue_summary');assert partial['run']==['cpue_summary','cpue_report']
assert full['records']['assessment_report']==partial['records']['assessment_report']
prep=execute('prepare_a');assert len(prep['run'])==5
assert full['records']['cpue_a']==prep['records']['cpue_a']
settings['min_hooks_a']=1200
manual=execute('cpue_a','manual',prep);assert len(manual['run'])==8
bundle=request('/bundle',session=session);assert bundle['bundle']
import base64
(ROOT/'.state/online-run.zip').write_bytes(base64.b64decode(bundle['bundle']))
other=request('/session',{})
try:request('/state?session='+session['id'],session=other)
except RuntimeError:pass
else:raise AssertionError('Reader isolation failed')
(ROOT/'.test-output').mkdir(exist_ok=True)
(ROOT/'.test-output/online-checks.json').write_text(json.dumps({'checks':checks,'session_isolation':'passed'},indent=2))
print('PASS: actual hosted full, partial, repeated and manual execution; reader isolation.',flush=True)
