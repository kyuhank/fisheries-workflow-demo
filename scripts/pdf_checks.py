"""Browser-test custody checks for displayed PDFs and preserved report HTML."""
import base64
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata


def expected_record(page, key):
    record = page.evaluate('(key) => structuredClone(records[key])', key)
    assert record and record['job'] == key, key
    assert record['run_id'] and record['signature'], key
    assert re.fullmatch(r'[a-f0-9]{64}', record['outputs']['report.pdf']), key
    return record


def assert_pdf_output(page, key, expected, phrases=(), save=False, open_link=False):
    page.wait_for_function("key => $('output-dialog').open && currentOutput?.record?.job === key",
                           arg=key, timeout=15000)
    output = page.evaluate('currentOutput')
    record = output['record']
    current = expected_record(page, key)
    for actual in (record, current):
        assert all(actual[field] == expected[field] for field in ('job', 'run_id', 'signature')), key
        assert actual['outputs']['report.pdf'] == expected['outputs']['report.pdf'], key
    checksum = expected['outputs']['report.pdf']
    decoded = base64.b64decode(output['pdf_base64'], validate=True)
    assert decoded.startswith(b'%PDF-') and hashlib.sha256(decoded).hexdigest() == checksum, key
    if 'pdf_sha256' in output:
        assert output['pdf_sha256'] == checksum, key
    rendering = record['report_rendering']
    assert rendering['engine'] == 'Quarto' and rendering['quarto_executed'] is True, key
    assert rendering['view'] == 'report.pdf', key
    assert page.locator('#output-title').inner_text() == page.evaluate('(key) => byKey[key].title', key), key
    assert page.locator('[data-output="report"]').inner_text() == ('Report' if key.endswith('_report') else 'Results'), key
    frame = page.locator('#output-frame')
    assert frame.is_visible() and frame.get_attribute('src').startswith('blob:'), key
    assert frame.get_attribute('srcdoc') is None and frame.get_attribute('sandbox') is None, key
    link = page.locator('#open-output-pdf')
    assert link.is_visible() and link.get_attribute('href') == frame.get_attribute('src'), key
    assert page.locator('#save-output').inner_text() == 'Save PDF', key
    encoded = frame.evaluate("""async frame => {
      const response = await fetch(frame.src);
      if (!response.ok) throw Error('Displayed PDF Blob is unavailable');
      const bytes = new Uint8Array(await response.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 32768)
        binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      return btoa(binary);
    }""")
    displayed = base64.b64decode(encoded, validate=True)
    assert displayed == decoded and hashlib.sha256(displayed).hexdigest() == checksum, key
    parsed = subprocess.run(['pdftotext', '-layout', '-', '-'], input=displayed,
                            capture_output=True, timeout=10)
    assert parsed.returncode == 0, (key, 'pdftotext failed', parsed.stderr.decode(errors='replace')[:300])
    text = ' '.join(unicodedata.normalize('NFKC', parsed.stdout.decode()).split())
    assert text, (key, 'Displayed PDF has no readable text')
    for phrase in phrases:
        assert phrase in text, (key, phrase)
    if save:
        with tempfile.TemporaryDirectory(prefix='pdf-check-') as directory:
            with page.expect_download() as download:
                page.locator('#save-output').click()
            assert download.value.suggested_filename == key + '-results.pdf', key
            path = Path(directory) / 'report.pdf'
            download.value.save_as(path)
            assert path.read_bytes() == displayed, key
    if open_link:
        with page.expect_popup() as opened:
            link.click()
        popup = opened.value
        popup.wait_for_url(frame.get_attribute('src'), timeout=10000)
        assert popup.url == frame.get_attribute('src'), key
        popup.close()
    return text, output


@contextmanager
def verified_html(page, output):
    assert hashlib.sha256(output['html'].encode()).hexdigest() == output['record']['outputs']['report.html'], output['record']['job']
    context = page.context.browser.new_context(offline=True, viewport=page.viewport_size)
    preview = context.new_page()
    try:
        preview.set_content(output['html'])
        yield preview
    finally:
        context.close()


def close_pdf_output(page):
    page.locator('#output-close').click()
    page.wait_for_function("!$('output-dialog').open && outputPdfUrl === null && outputPdfBytes === null && $('output-frame').src === 'about:blank'")


def check_pdf_rejections(page):
    """Exercise actual app guards with current genuine saved PDFs, then restore UI."""
    page.evaluate("""() => {
      window.__pdfCheckState = {call, mode, modeVersion, records};
      window.__beginPdfCheck = missingHash => {
        mode = 'cloud'; records = structuredClone(payload.saved.records);
        if (missingHash) delete records.cpue_a.outputs['report.pdf'];
        status('', 'PDF check pending', 'Awaiting the test response');
        call = () => new Promise(resolve => {window.__pdfCheckResolve = resolve;});
        window.__pdfCheckPending = openOutput('cpue_a');
      };
    }""")
    try:
        for field in ('job', 'run_id', 'signature', 'hash', 'corrupt', 'missing-hash'):
            page.evaluate("field => __beginPdfCheck(field === 'missing-hash')", field)
            page.evaluate("""async field => {
              let output = structuredClone(payload.saved.outputs.cpue_a);
              if (field === 'job') output = structuredClone(payload.saved.outputs.cpue_b);
              else if (field === 'hash') output.record.outputs['report.pdf'] = '0'.repeat(64);
              else if (field === 'corrupt') output.pdf_base64 = btoa('corrupt PDF bytes');
              else if (field === 'missing-hash') {
                delete output.record.outputs['report.pdf'];
              } else output.record[field] = 'wrong';
              __pdfCheckResolve(output); await __pdfCheckPending;
            }""", field)
            assert not page.locator('#output-dialog').is_visible(), field
            assert page.locator('#status-title').inner_text() == 'This output is unavailable', field
            message = page.locator('#status-message').inner_text()
            reason = 'no recorded checksum' if field == 'missing-hash' else 'differs from its recorded checksum' if field == 'corrupt' else 'different run'
            assert reason in message, (field, message)
        for field in ('mode', 'run_id', 'signature', 'hash'):
            page.evaluate('__beginPdfCheck()')
            page.evaluate("""async field => {
              if (field === 'mode') await activateMode('saved');
              else if (field === 'hash') records.cpue_a.outputs['report.pdf'] = '1'.repeat(64);
              else records.cpue_a[field] = 'newer';
              status('', 'Newer PDF check', 'Keep the current state');
              __pdfCheckResolve(structuredClone(payload.saved.outputs.cpue_a));
              await __pdfCheckPending;
            }""", field)
            assert not page.locator('#output-dialog').is_visible(), field
            assert page.locator('#status-title').inner_text() == 'Newer PDF check', field
        page.evaluate('__beginPdfCheck()')
        expected = expected_record(page, 'cpue_a')
        page.evaluate('async () => {__pdfCheckResolve(structuredClone(payload.saved.outputs.cpue_a)); await __pdfCheckPending;}')
        assert_pdf_output(page, 'cpue_a', expected, phrases=('CPUE',))
        close_pdf_output(page)
    finally:
        page.evaluate("""() => {
          ({call, mode, modeVersion, records} = __pdfCheckState);
          delete window.__pdfCheckState; delete window.__beginPdfCheck;
          delete window.__pdfCheckResolve; delete window.__pdfCheckPending;
          render();
        }""")
