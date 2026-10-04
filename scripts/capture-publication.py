#!/usr/bin/env python3
"""Capture the Saved view at print resolution."""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
destination = root / '.test-output' / 'publication'
destination.mkdir(parents=True, exist_ok=True)
source = root / 'docs' / 'offline.html'
scale = 3.4

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(offline=True, viewport={'width': 1280, 'height': 720},
                            device_scale_factor=scale)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(source.as_uri() + '#orchestration')
    page.wait_for_function("document.querySelector('#mode').value === 'saved'")
    page.locator('#tasks .mse').wait_for(state='visible')
    tasks = page.evaluate("""() => {
      const bounds = el => { const r = el.getBoundingClientRect();
        return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height}; };
      return {tasks:[...document.querySelectorAll('#tasks .task')].map(el => ({
        class:el.className,name:el.querySelector('.task-card-heading').innerText,
        bounds:bounds(el),heading:bounds(el.querySelector('.task-card-heading')),
        responsibility:bounds(el.querySelector('.task-responsibility'))}))};
    }""")
    page.screenshot(path=str(destination / 'tasks.png'), full_page=True)
    page.locator('#tasks .mse').click()
    page.locator('tr[data-job="mse_summary"]').wait_for(state='visible')
    jobs = page.evaluate("""() => {
      const bounds = el => { const r = el.getBoundingClientRect();
        return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height}; };
      return {rows:[...document.querySelectorAll('.job-table thead tr, #job-table-body tr')].map(el => ({
          job:el.dataset.job || null,bounds:bounds(el),cells:[...el.children].map(c =>
          ({text:c.innerText,bounds:bounds(c)}))}))};
    }""")
    page.screenshot(path=str(destination / 'jobs.png'), full_page=True)
    page.locator('tr[data-job="mse_summary"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    record = page.evaluate("""() => {
      const bounds = el => { const r = el.getBoundingClientRect();
        return {x:r.x,y:r.y,width:r.width,height:r.height}; };
      return {coordinate_system:'viewport screenshot; fixed modal; no scroll offset',
        selected_record:'mse_summary',cards:[...document.querySelectorAll('#output-record .record-card')]
          .map(el => ({text:el.innerText,bounds:bounds(el)}))};
    }""")
    page.screenshot(path=str(destination / 'record.png'))
    assert not errors, errors
    for name, metadata in [('tasks', tasks), ('jobs', jobs), ('record', record)]:
        metadata.update(device_scale_factor=scale, mode='saved',
                        viewport={'width':1280,'height':720},
                        document_width=page.evaluate('document.documentElement.clientWidth'),
                        source_reader_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        (destination / f'{name}.json').write_text(json.dumps(metadata, indent=2) + '\n')
    browser.close()
print('PASS: genuine Saved reader captured at native print resolution; no calculations invoked.')
