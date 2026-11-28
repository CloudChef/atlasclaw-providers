const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const uiPath = path.join(__dirname, '..', 'ui');
const source = fs.readFileSync(path.join(uiPath, 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(uiPath, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(uiPath, 'style.css'), 'utf8');

function extractFunction(name, dependencies = {}) {
  const signature = `function ${name}(`;
  const start = source.indexOf(signature);
  assert.notEqual(start, -1, `${name} must remain a standalone helper`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) {
      return new Function(...Object.keys(dependencies), `return (${source.slice(start, index + 1)});`)(...Object.values(dependencies));
    }
  }
  assert.fail(`${name} must have a complete body`);
}

test('the global upload is scoped to audit while shared materials keeps its own upload', () => {
  assert.match(html, /<button[^>]*id="uploadButton"[\s\S]*?<\/button>/);
  assert.match(html, /<section id="standardsView"[\s\S]*?id="standardUploadButton"/);
  const state = {};
  const button = { hidden: false };
  const auditView = { hidden: false };
  const standardsView = { hidden: false };
  const tabs = [{ dataset: { view: 'audit' }, classList: { toggle() {} }, setAttribute() {} }];
  const switchView = extractFunction('switchView', {
    state, els: { auditView, standardsView, uploadButton: button, viewTabs: tabs }, loadStandards() {},
  });
  switchView('standards');
  assert.equal(button.hidden, true);
  assert.equal(standardsView.hidden, false);
  switchView('audit');
  assert.equal(button.hidden, false);
  assert.equal(auditView.hidden, false);
});

test('document row keeps result links in Result and only audit, retry, delete in Actions', () => {
  const locale = {
    startAudit: 'Start audit', viewProgress: 'View progress', viewResult: 'View result',
    viewDetails: 'View details', downloadDesensitizedPdf: 'Download desensitized PDF',
    downloadReportPdf: 'Download audit PDF', downloadReport: 'Download report',
    retry: 'Retry', delete: 'Delete',
  };
  const escapeHtml = extractFunction('escapeHtml');
  const t = key => locale[key] || key;
  const serverUrl = value => value || '';
  const resultText = extractFunction('resultText', { t });
  const resultActions = extractFunction('resultActions', { escapeHtml, serverUrl, t });
  const actionButtons = extractFunction('actionButtons', { escapeHtml, t });
  const renderDocumentRow = extractFunction('renderDocumentRow', {
    resultText, resultActions, actionButtons, escapeHtml,
    formatTime: () => 'time', statusLabel: () => 'Completed',
  });
  const row = renderDocumentRow({
    id: 'doc-1', file_name: 'sample.pdf', status: 'completed', created_at: '',
    findings_total: 2, findings_review: 1, report_available: true, desensitized_available: true,
    report_format: 'pdf', urls: { report_download: '/report.pdf', desensitized_download: '/safe.pdf' },
    actions: ['view_result', 'reaudit', 'delete'],
  });

  assert.match(row, /class="result-cell"[\s\S]*findings[\s\S]*data-action="result"[\s\S]*data-action="download-desensitized"[\s\S]*data-action="download-report"/);
  const actionsCell = row.match(/<td class="actions-cell">([\s\S]*?)<\/td>/)?.[1] || '';
  assert.deepEqual([...actionsCell.matchAll(/data-action="([^"]+)"/g)].map(match => match[1]), ['audit', 'delete']);
  const resultCell = row.match(/<td class="result-cell">([\s\S]*?)<\/td>/)?.[1] || '';
  assert.deepEqual([...resultCell.matchAll(/data-action="([^"]+)"/g)].map(match => match[1]), ['result', 'download-desensitized', 'download-report']);

  const legacyReport = resultActions({
    status: 'running', actions: ['view_progress'], report_available: true, desensitized_available: false,
    report_format: 'html', urls: { report_download: '/legacy-report' },
  });
  assert.match(legacyReport, /View progress[\s\S]*Download report/);

  const pendingRow = renderDocumentRow({
    id: 'doc-pending', file_name: 'prepared.pdf', status: 'pending', actions: ['start_audit'],
    report_available: true, desensitized_available: false, urls: { report_download: '/prepared.pdf' },
  });
  assert.match(pendingRow, /class="result-cell"[\s\S]*data-action="download-report"/);
  const pendingActions = pendingRow.match(/<td class="actions-cell">([\s\S]*?)<\/td>/)?.[1] || '';
  assert.match(pendingActions, /data-action="audit"/);

  const failedResult = resultActions({ status: 'failed', actions: [], report_available: false, desensitized_available: false });
  assert.match(failedResult, /View details/);
});

test('small screens retain the Result column and table links remain delegated', () => {
  assert.doesNotMatch(css, /\.document-table th:nth-child\(4\),\s*\.document-table td:nth-child\(4\)\s*\{\s*display:\s*none;/);
  assert.match(source, /els\.rows\.addEventListener\('click',[\s\S]*?data-action[\s\S]*?download-desensitized[\s\S]*?download-report/);
});

test('zero confirmed findings with pending findings shows the review count', () => {
  const locale = {
    noFindings: 'No findings',
    findings: '{total} finding(s) · {review} to review',
    incompleteFindings: '0 confirmed findings · {review} to review',
    incompleteNoFindings: 'Report generated; some conclusions are unclear. Review the pending items.',
  };
  const t = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value), locale[key] || key,
  );
  const resultText = extractFunction('resultText', { t });

  assert.equal(resultText({ status: 'completed', findings_total: 0, findings_review: 46 }), '0 confirmed findings · 46 to review');
  assert.equal(resultText({ status: 'completed', completion_status: 'needs_review', findings_total: 3, findings_review: 1 }), '3 finding(s) · 1 to review');
  assert.notEqual(resultText({ status: 'completed', findings_total: 0, findings_review: 0 }), '0 confirmed findings · 0 to review');
});

test('incomplete result cannot render green on a Pass verdict and keeps result table', () => {
  const locale = {
    resultsOverview: 'Overall: {verdict} · Pass {pass} · Fail {fail} · Review {review} · N/A {na}',
    incompleteNoFindings: 'Report generated; some conclusions are unclear. Review the pending items.',
    colRule: 'Rule', colCheck: 'Check', colVerdict: 'Verdict', colPage: 'Page',
    colDetail: 'Issue and remediation', colEvidence: 'Evidence', evidenceMissing: 'None',
    verdictPass: 'Pass', verdictFail: 'Fail', verdictReview: 'Review', verdictNA: 'N/A',
    pageValue: 'Page {page}',
  };
  const t = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, value), locale[key] || key,
  );
  const renderResults = extractFunction('renderResults', {
    t, escapeHtml: extractFunction('escapeHtml'), evidenceUrl: () => '',
    verdictLabel: extractFunction('verdictLabel', { t }),
  });
  const html = renderResults({
    document_id: 'doc-1', verdict: '通过', completion_status: 'needs_review',
    counts: { PASS: 0, FAIL: 0, REVIEW: 46, NA: 0 },
    results: [{ rule: 'R01', title: 'Coverage', verdict: 'REVIEW', reason: 'No conclusion' }],
  });

  assert.match(html, /class="result-overview bad"/);
  assert.match(html, /Report generated; some conclusions are unclear/);
  assert.match(html, /class="result-table"/);
  assert.match(html, /No conclusion/);
  assert.match(css, /\.result-incomplete-note/);
});
