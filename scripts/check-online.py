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

def execute(start,handover='connected',previous=None,expected_boundaries=None):
 result=request('/run',{'start':start,'settings':settings,'handover':handover},session)
 print('Requested',start,result['id'],flush=True)
 cursor=0;deadline=time.monotonic()+600;transferred=False;pending=None;events=[];status_deadline=None
 boundaries=[];confirmed=[];reports_before_transfer=[]
 while time.monotonic()<deadline:
  update=request('/state?after='+str(cursor),session=session)
  for row in update['events']:
   cursor=row['id'];e=row['event'];events.append(e);print(e.get('job','workflow'),e['state'],e.get('title',''),flush=True)
   if e['state']=='handover':
    pending=e
    boundaries.append(e['boundary'])
    expected={'data':['cpue_a','cpue_b'],'cpue':['prepare_a'] if previous else ['prepare_a','prepare_b'],
              'assessment':['mse_prepare']}[e['boundary']]
    assert e['group']==expected,(e,expected)
  run=update['run']
  if run and run['status'] in ('failed','expired'):raise RuntimeError(run.get('error') or run['status'])
  report={'cpue':'cpue_report','assessment':'assessment_report'}.get(pending['boundary']) if pending else None
  if pending and (report is None or any(e.get('job')==report and e['state']=='complete' for e in events)):
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
   if pending['boundary']=='assessment':
    planned=next((e['run'] for e in events if e['state']=='plan'),[])
    completed={e.get('job') for e in events if e['state']=='complete'}
    assert all(key in completed for key in SPEC['mse_prepare']['parents'] if key in planned)
    assert not any(SPEC.get(e.get('job'),{}).get('module')=='mse' and e['state']=='running' for e in events)
   if previous:
    key='mse_prepare' if pending['boundary']=='assessment' else 'assessment_a1'
    old=request('/output?job='+key,session=session)
    assert old['record']==previous['records'][key]
   confirmed.append(pending['boundary'])
   if report:reports_before_transfer.append(pending['boundary'])
   request('/transfer',{'connect':False},session);transferred=True;pending=None;status_deadline=None
  if run and run['status']=='complete':
   if handover=='manual':assert transferred,'Manual execution must require confirmation'
   if expected_boundaries is not None:
    received=[e['boundary'] for e in events if e['state']=='received']
    assert boundaries==confirmed==received==expected_boundaries,(boundaries,confirmed,received,expected_boundaries)
   positions={(e.get('job'),e['state']):i for i,e in enumerate(events)}
   for group in STAGES:
    completed=[positions[(key,'complete')] for key in group if (key,'complete') in positions]
    for key,job in SPEC.items():
     if completed and set(job['parents']).intersection(group) and (key,'running') in positions:
      assert max(completed)<positions[(key,'running')],(group,key)
   value=run['result'];checks.append({'start':start,'handover':handover,'github_run':run['github_run'],'commit':run['commit_sha'],'executed':value['run'],'retained':value['retained'],'manual_transfer_checked':transferred})
   checks[-1]['peer_barriers_checked']=True
   checks[-1]['manual_transfer_boundaries']=confirmed
   checks[-1]['report_completed_before_cpue_transfer']='cpue' in reports_before_transfer
   checks[-1]['report_completed_before_assessment_transfer']='assessment' in reports_before_transfer
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
 full=execute('submission','manual',expected_boundaries=['data','cpue','assessment']);assert len(full['run'])==22
 partial=execute('cpue_summary',expected_boundaries=[]);assert partial['run']==['cpue_summary','cpue_report']
 assert full['records']['assessment_report']==partial['records']['assessment_report']
 prep=execute('prepare_a',expected_boundaries=[]);assert len(prep['run'])==11
 assert full['records']['cpue_a']==prep['records']['cpue_a']
 settings['min_hooks_a']=1200
 manual=execute('cpue_a','manual',prep,expected_boundaries=['cpue','assessment']);assert len(manual['run'])==14
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
