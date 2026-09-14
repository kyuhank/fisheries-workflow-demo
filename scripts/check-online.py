"""Optional integration check: run the online demo without a reader login."""
import json,time,urllib.request,urllib.error,sys
from pathlib import Path
BASE='https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workflow.spec import SPEC,STAGES

def request(path,body=None,session=None):
 headers={'Content-Type':'application/json'}
 if session:
  path+=('&' if '?' in path else '?')+'session='+session['id'];headers['Authorization']='Bearer '+session['token']
 r=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(r,timeout=40) as response:return json.load(response)
 except urllib.error.HTTPError as e:raise RuntimeError(str(e.code)+' '+json.load(e).get('error','Request failed'))

session=None
settings={'last_year':2023,'min_hooks_a':0,'mortality_2':.3,'mse':True}
checks=[]

def execute(start,handover='connected',previous=None):
 result=request('/run',{'start':start,'settings':settings,'handover':handover},session)
 print('Requested',start,result['id'],flush=True)
 cursor=0;deadline=time.monotonic()+600;transferred=False;pending=None;events=[];status_deadline=None
 while time.monotonic()<deadline:
  update=request('/state?after='+str(cursor),session=session)
  for row in update['events']:
   cursor=row['id'];e=row['event'];events.append(e);print(e.get('job','workflow'),e['state'],e.get('title',''),flush=True)
   if e['state']=='handover':
    pending=e
    expected=['cpue_a','cpue_b'] if e['boundary']=='data' else (['prepare_a'] if previous else ['prepare_a','prepare_b'])
    assert e['group']==expected,(e,expected)
  run=update['run']
  if run and run['status'] in ('failed','expired'):raise RuntimeError(run.get('error') or run['status'])
  if pending and (pending['boundary']=='data' or any(e.get('job')=='cpue_report' and e['state']=='complete' for e in events)):
   # /state reads the run before the events. A handover committed between those
   # reads can appear alongside the preceding running status in one poll.
   # Wait for a fresh status; a persistent mismatch still fails this check.
   if run['status']!='handover':
    if status_deadline is None:status_deadline=time.monotonic()+15
    if run['status']=='complete' or time.monotonic()>=status_deadline:
     raise AssertionError('Reporting must leave the pending transfer available: '+run['status'])
    time.sleep(1)
    continue
   assert not any(e.get('job') in pending['group'] and e['state']=='running' for e in events)
   if previous:
    old=request('/output?job=assessment_a1',session=session)
    assert old['record']==previous['records']['assessment_a1']
   request('/transfer',{'connect':False},session);transferred=True;pending=None;status_deadline=None
  if run and run['status']=='complete':
   if handover=='manual':assert transferred,'Manual execution must require confirmation'
   positions={(e.get('job'),e['state']):i for i,e in enumerate(events)}
   for group in STAGES:
    completed=[positions[(key,'complete')] for key in group if (key,'complete') in positions]
    for key,job in SPEC.items():
     if completed and set(job['parents']).intersection(group) and (key,'running') in positions:
      assert max(completed)<positions[(key,'running')],(group,key)
   value=run['result'];checks.append({'start':start,'handover':handover,'github_run':run['github_run'],'commit':run['commit_sha'],'executed':value['run'],'retained':value['retained'],'manual_transfer_checked':transferred})
   checks[-1]['peer_barriers_checked']=True
   checks[-1]['report_completed_before_cpue_transfer']=handover=='manual'
   checks[-1]['events']=[{key:e[key] for key in ('job','state','group','boundary') if key in e} for e in events]
   print('Completed GitHub run',run['github_run'],'jobs',len(value['run']),flush=True)
   return value
  time.sleep(1)
 raise TimeoutError('Online execution timed out')

def main():
 global session
 (ROOT/'.state').mkdir(exist_ok=True)
 session=request('/session',{})
 p=ROOT/'.state/test-reader.json';p.write_text(json.dumps(session));p.chmod(0o600)
 full=execute('submission','manual');assert len(full['run'])==22
 partial=execute('cpue_summary');assert partial['run']==['cpue_summary','cpue_report']
 assert full['records']['assessment_report']==partial['records']['assessment_report']
 prep=execute('prepare_a');assert len(prep['run'])==11
 assert full['records']['cpue_a']==prep['records']['cpue_a']
 settings['min_hooks_a']=1200
 manual=execute('cpue_a','manual',prep);assert len(manual['run'])==14
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

if __name__=='__main__':main()
