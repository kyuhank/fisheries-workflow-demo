const payload = JSON.parse(document.getElementById('demo-payload').textContent);
const $ = id => document.getElementById(id);
const worker = new Worker(URL.createObjectURL(new Blob([$('worker-source').textContent], {type: 'text/javascript'})));
const pending = new Map();
let sequence = 0, planVersion = 0, jobs = payload.jobs, records = {}, states = {}, plan = null;
let selected = 'submission', busy = false, ready = false, currentOutput = null, latestRun = '', selectedTask = '';
let mode = 'live', liveState = null;
const byKey = Object.fromEntries(jobs.map(job => [job.key, job]));
const messages = [];

function call(type, data = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, {resolve, reject});
    worker.postMessage({id, type, payload: data});
  });
}

function settings() {
  return {last_year: Number($('snapshot').value), min_hooks_a: Number($('filter').value), mortality_2: Number($('mortality').value)};
}

function status(kind, title, message) {
  $('status').className = 'status ' + kind;
  $('status-title').textContent = title;
  $('status-message').textContent = message;
  $('status-icon').className = 'status-icon' + (kind === 'running' ? ' spinner' : '');
  $('status-icon').textContent = kind === 'running' ? '' : kind === 'failed' ? '!' : kind === 'complete' ? '✓' : '·';
}

function stageStatus(key) {
  if (states[key]) return states[key];
  if (!records[key]) return 'waiting';
  return records[key].run_id === latestRun ? 'complete' : 'retained';
}

const labels = {waiting: 'Waiting', running: 'Running', complete: 'Complete', retained: 'Retained', failed: 'Failed', returned: 'Correction'};
const symbols = {waiting: '○', complete: '✓', retained: '↶', failed: '!', returned: '↶'};

function badge(key) {
  const state = stageStatus(key), span = document.createElement('span');
  span.className = 'state';
  const symbol = document.createElement('span');
  symbol.className = 'symbol' + (state === 'running' ? ' spinner' : '');
  symbol.textContent = symbols[state] || '';
  span.append(symbol, document.createTextNode(labels[state] || state));
  return span;
}

function selectJob(key) {
  selected = key;
  $('selection-title').textContent = byKey[key].title;
  $('selection-description').textContent = byKey[key].description;
  if (!busy && mode === 'live') refreshPlan();
  else render();
}

function jobCard(key) {
  const job = byKey[key], card = document.createElement('div'), state = stageStatus(key);
  card.className = 'job ' + state + (selected === key ? ' selected' : '') + (plan?.run.includes(key) ? ' in-path' : '');
  card.dataset.job = key; card.tabIndex = 0; card.setAttribute('role', 'button');
  card.setAttribute('aria-label', job.title + ': ' + (labels[state] || state) + '. Select starting job.');
  card.onclick = () => selectJob(key);
  card.onkeydown = event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); selectJob(key);}};
  const title = document.createElement('h3'); title.textContent = job.title;
  const origin = document.createElement('div'); origin.className = 'origin';
  origin.textContent = state === 'retained' && records[key] ? records[key].run_id + ' · unchanged' : '';
  const view = document.createElement('button'); view.className = 'view'; view.textContent = 'View ›';
  view.disabled = !records[key]; view.setAttribute('aria-label', 'View ' + job.title + ' output');
  view.onclick = event => {event.stopPropagation(); openOutput(key);};
  view.onkeydown = event => event.stopPropagation();
  card.append(title, badge(key), origin, view);
  return card;
}

function render() {
  $('workflow-view').replaceChildren();
  const groups = [
    ['data', 'Data management', ['submission','qc','database','extract']],
    ['cpue', 'CPUE analysis', [['cpue_a','cpue_b'],'cpue_summary','cpue_report']],
    ['assessment', 'Stock assessment', [['prepare_a','prepare_b'],['assessment_a1','assessment_a2'],['assessment_b1','assessment_b2'],'assessment_summary','assessment_report']]
  ];
  groups.forEach(([module, title, entries], i) => {
    const panel = document.createElement('article'); panel.className = 'module ' + module;
    const header = document.createElement('header'), number = document.createElement('span'), heading = document.createElement('h2');
    number.className = 'number'; number.textContent = i + 1; heading.textContent = title; header.append(number, heading); panel.append(header);
    for (const entry of entries) {
      if (Array.isArray(entry)) {const pair = document.createElement('div'); pair.className = 'pair'; pair.append(...entry.map(jobCard)); panel.append(pair);}
      else panel.append(jobCard(entry));
    }
    $('workflow-view').append(panel);
  });
  $('job-table-body').replaceChildren();
  $('tasks').replaceChildren();
  for (const [module, title] of groups) {
    const members = jobs.filter(job => job.module === module), active = members.filter(job => stageStatus(job.key) === 'running');
    const button = document.createElement('button'); button.className = 'task ' + module + (active.length ? ' running' : '') + (selectedTask === module ? ' active' : '');
    const name = document.createElement('strong'); name.textContent = title;
    const summary = document.createElement('span'); summary.textContent = active.length ? 'Running · ' + active.map(job => job.title).join(', ') : members.filter(job => records[job.key]).length + ' / ' + members.length + ' outputs available';
    button.append(name, summary); button.onclick = () => {selectedTask = module; $('task-title').textContent = title; render();}; $('tasks').append(button);
  }
  for (const job of jobs) {
    if (selectedTask && job.module !== selectedTask) continue;
    const row = document.createElement('tr'); row.className = stageStatus(job.key); row.dataset.job = job.key;
    for (const value of [job.title, job.owner]) {const cell = document.createElement('td'); cell.textContent = value; row.append(cell);}
    const inputs = document.createElement('small'); inputs.className = 'job-inputs'; inputs.textContent = job.parents.length ? 'Uses: ' + job.parents.map(key => byKey[key].title).join(' · ') : 'Starts with the supplied records'; row.firstChild.append(inputs);
    const state = document.createElement('td'); state.append(badge(job.key)); row.append(state);
    const origin = document.createElement('td'); origin.textContent = records[job.key]?.run_id || '—'; row.append(origin);
    const output = document.createElement('td'), button = document.createElement('button');
    button.className = 'quiet'; button.textContent = 'View output'; button.disabled = !records[job.key]; button.onclick = () => openOutput(job.key); output.append(button); row.append(output);
    $('job-table-body').append(row);
  }
  $('run').disabled = !ready || busy || !plan || mode === 'saved';
  $('run').hidden = mode === 'saved';
  $('run').textContent = busy ? 'Running…' : selected === 'submission' ? 'Run full workflow →' : 'Run from this job →';
  $('download').disabled = busy || !Object.keys(records).length;
  $('reset').disabled = busy || !ready || mode === 'saved';
  $('mode').disabled = busy;
  for (const id of ['snapshot','filter','mortality']) $(id).disabled = busy || mode === 'saved';
  if (mode === 'saved') {
    $('completion').textContent = '16 saved outputs';
    $('reuse-message').textContent = 'A preserved execution. Switch to Live analysis to calculate your own results.';
  } else if (plan) {
    $('completion').textContent = `${plan.run.length} jobs to run · ${plan.retained.length} retained`;
    const parentNames = byKey[selected].parents.filter(key => plan.retained.includes(key)).map(key => `${byKey[key].title} (${records[key]?.run_id})`);
    $('reuse-message').textContent = parentNames.length ? 'Uses saved inputs: ' + parentNames.join(' · ') : plan.retained.length ? 'Other results keep their original run and files.' : '';
    if (plan.changed.length && selected !== 'submission') $('reuse-message').textContent += ' Missing or changed inputs are rebuilt first.';
  }
}

async function refreshPlan() {
  if (!ready || busy || mode !== 'live') return;
  const version = ++planVersion;
  $('run').disabled = true;
  try {const next = await call('plan', {start: selected, settings: settings()}); if (version === planVersion) {plan = next; render();}}
  catch (error) {showError(error);}
}

function showError(error) {
  busy = false;
  status('failed', 'The analysis stopped', String(error));
  render();
}

function log(event) {
  const name = byKey[event.job]?.title || 'Workflow';
  messages.push(`${name} · ${event.message || event.state}`);
  $('execution-log').textContent = messages.join('\n');
  $('execution-log').scrollTop = $('execution-log').scrollHeight;
}

worker.onmessage = ({data}) => {
  if (data.type === 'event') {
    const event = data.event;
    if (event.state === 'plan') {
      plan = event; latestRun = event.run_id; $('run-id').textContent = latestRun;
      states = Object.fromEntries(jobs.map(job => [job.key, plan.run.includes(job.key) ? 'waiting' : 'retained']));
    } else {
      states[event.job] = event.state;
      if (event.record) records[event.job] = event.record;
      log(event);
      status(event.state === 'failed' ? 'failed' : 'running', byKey[event.job].title, event.message);
    }
    render(); return;
  }
  const request = pending.get(data.id);
  if (!request) return;
  pending.delete(data.id);
  if (data.type === 'error') request.reject(new Error(data.error)); else request.resolve(data.value);
};
worker.onerror = event => {ready = false; for (const task of pending.values()) task.reject(new Error(event.message)); pending.clear(); showError(event.message);};

$('run').onclick = async () => {
  if (!ready || busy) return;
  busy = true; messages.length = 0; $('execution-log').textContent = '';
  status('running', 'Starting the selected work', 'Checking saved inputs and the selected settings.'); render();
  try {
    const result = await call('run', {start: selected, settings: settings()});
    records = result.records; busy = false; latestRun = result.run_id;
    status('complete', 'Results are ready', `${result.run.length} jobs completed · ${result.retained.length} retained unchanged. Open a job to inspect its output.`);
    $('completion').textContent = `${result.run.length} completed · ${result.retained.length} retained`;
    await refreshPlan();
  } catch (error) {showError(error); await refreshPlan();}
};
for (const id of ['snapshot','filter','mortality']) $(id).onchange = refreshPlan;
$('reset').onclick = async () => {
  const result = await call('reset'); records = result.records; states = {}; latestRun = ''; selected = 'submission';
  $('snapshot').value = '2023'; $('filter').value = '0'; $('mortality').value = '0.30'; $('run-id').textContent = '';
  messages.length = 0; $('execution-log').textContent = 'No execution yet.';
  status('', 'Ready to run', 'Begin with data submission, or select an analysis job.'); selectJob('submission');
};
for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => {
  for (const other of document.querySelectorAll('[data-tab]')) {const active = other === button; other.classList.toggle('active', active); other.setAttribute('aria-selected', active);}
  $('workflow-view').hidden = button.dataset.tab !== 'workflow'; $('jobs-view').hidden = button.dataset.tab !== 'jobs';
};
function showRecord(show) {$('record-panel').hidden = !show; $('record-toggle').textContent = show ? 'Hide record' : 'Show record'; $('record-toggle').setAttribute('aria-expanded', show);}
$('record-toggle').onclick = () => showRecord($('record-panel').hidden);
$('record-close').onclick = () => showRecord(false);
$('all-tasks').onclick = () => {selectedTask = ''; $('task-title').textContent = 'All jobs'; render();};

function download(name, bytes, type) {
  const url = URL.createObjectURL(new Blob([bytes], {type})), a = document.createElement('a');
  a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
}
$('download').onclick = async () => {
  const bytes = Uint8Array.from(atob(mode === 'saved' ? payload.saved.bundle : await call('download')), char => char.charCodeAt(0));
  download('fisheries-workflow-run.zip', bytes, 'application/zip');
};
function displayOutput(title, output, kind = 'Job output') {
  currentOutput = output; $('output-title').textContent = title; $('output-kind').textContent = kind;
  $('output-frame').srcdoc = output.html; $('output-frame').hidden = false; $('output-json').hidden = true;
  document.querySelectorAll('[data-output]').forEach(button => {button.classList.toggle('active', button.dataset.output === 'report'); button.disabled = button.dataset.output !== 'report' && !output.record;});
  $('output-dialog').showModal();
}
async function openOutput(key) {
  try {displayOutput(byKey[key].title, mode === 'saved' ? payload.saved.outputs[key] : await call('view', {job: key}), mode === 'saved' ? 'Saved example output' : 'Job output');}
  catch (error) {showError(error);}
}
$('example').onclick = () => displayOutput('Assessment report', {html: payload.example}, 'Preserved example');
$('licences').onclick = () => {
  const pre = document.createElement('pre'); pre.textContent = payload.notices;
  displayOutput('Sources and licences', {html: '<!doctype html><meta charset="utf-8"><style>body{padding:24px;font:14px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>' + pre.outerHTML}, 'Preserved software');
};
$('output-close').onclick = () => $('output-dialog').close();
$('output-dialog').onclick = event => {if (event.target === $('output-dialog')) {const box = event.target.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close();}};
for (const button of document.querySelectorAll('[data-output]')) button.onclick = () => {
  document.querySelectorAll('[data-output]').forEach(other => other.classList.toggle('active', other === button));
  const report = button.dataset.output === 'report'; $('output-frame').hidden = !report; $('output-json').hidden = report;
  if (!report) $('output-json').textContent = button.dataset.output === 'log' ? currentOutput.record.log.join('\n') : JSON.stringify(currentOutput[button.dataset.output === 'data' ? 'output' : 'record'], null, 2);
};
$('save-output').onclick = () => download('analysis-output.html', currentOutput.html, 'text/html');
$('mode').onchange = async () => {
  mode = $('mode').value;
  if (mode === 'saved') {
    liveState = {records, states, latestRun, selected, messages: [...messages]};
    records = payload.saved.records;
    states = Object.fromEntries(jobs.map(job => [job.key, 'complete']));
    latestRun = 'Saved example'; plan = null;
    $('run-id').textContent = latestRun;
    messages.length = 0;
    payload.saved.events.forEach(log);
    status('', 'Explore a saved execution', 'Inspect every job, input, log and report. No calculation or internet connection is needed.');
  } else {
    if (liveState) {
      ({records, states, latestRun, selected} = liveState);
      messages.splice(0, messages.length, ...liveState.messages);
      $('execution-log').textContent = messages.join('\n') || 'No execution yet.';
    }
    $('run-id').textContent = latestRun;
    status('', 'Ready to run', 'Calculate results here using the preserved Python code.');
    selectJob(selected);
    await refreshPlan();
  }
  render();
};
render();
call('init', {runtime: payload.runtime, files: payload.files}).then(async result => {
  ready = true;
  if (mode === 'live') {
    records = result.records;
    status('', 'Ready to run', 'Begin with data submission, or select an analysis job.');
    await refreshPlan();
  }
}).catch(showError);
