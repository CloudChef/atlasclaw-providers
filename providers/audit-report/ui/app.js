/*
 *  Copyright 2026 Qianyun, Inc., All rights reserved.
 *  文件审核 provider UI (Provider Extension Standard v1).
 */

const MESSAGES = {
  'zh-CN': {
    upload: '上传文档',
    search: '搜索文档名称',
    allStatus: '全部状态',
    statusPending: '待审核',
    statusRunning: '审核中',
    statusCompleted: '审核完成',
    statusFailed: '解析失败',
    colName: '文档名称',
    colUploadedAt: '上传时间',
    colStatus: '处理状态',
    colResult: '审核结果',
    colActions: '操作',
    emptyTitle: '还没有文档',
    emptyBody: '点击右上角“上传文档”开始审核。',
    count: '共 {count} 份文档',
    startAudit: '开始审核',
    viewProgress: '查看进度',
    viewResult: '查看结果',
    downloadReport: '下载报告',
    reaudit: '重新审核',
    retry: '重试',
    delete: '删除',
    noFindings: '未发现问题',
    findings: '{total} 条问题 · {review} 条待复核',
    uploadTitle: '上传文档',
    dropzone: '拖拽 PDF / Word 到此处',
    dropzoneHint: '或点击选择文件（单个不超过 200 MiB）',
    cancel: '取消',
    confirmUpload: '开始上传',
    close: '关闭',
    openReport: '下载报告',
    colRule: '规则',
    colCheck: '检查项',
    colVerdict: '判定',
    colPage: '页码',
    colDetail: '问题与整改建议',
    colEvidence: '证据截图',
    evidenceMissing: '无',
    verdictPass: '通过',
    verdictFail: '不通过',
    verdictReview: '待复核',
    verdictNA: '不适用',
    resultsLoading: '正在加载审核结果…',
    resultsNotReady: '审核结果尚未生成',
    resultsOverview: '总评：{verdict} · 通过 {pass} · 不通过 {fail} · 待复核 {review} · 不适用 {na}',
    viewAudit: '文档审核',
    viewStandards: '审核标准库',
    uploadStandard: '上传标准',
    standardHint: '上传客户的规则/标准文档（支持 PDF、Word、Markdown、txt）。系统会自动编译成技能规则包并启用，所有开启该 provider 的人共用同一份规则库，下一次审核即生效。',
    colStandardName: '标准文件',
    colStandardRules: '规则数',
    colStandardStatus: '状态',
    colStandardUploadedAt: '上传时间',
    standardCount: '共 {count} 份标准',
    standardUploaded: '标准已上传',
    standardDeleted: '标准已删除',
    standardDeleteConfirm: '确定删除这份审核标准？',
    standardEmptyTitle: '还没有审核标准',
    standardEmptyBody: '点击右上角“上传标准”添加判定依据。',
    statusCompiling: '编译中',
    statusActive: '已启用',
    statusCompileFailed: '编译失败',
    recompile: '重新编译',
    recompileStarted: '已重新开始编译',
    unsupportedStandard: '只支持 PDF、Word、Markdown、txt 规则文档',
    download: '下载',
    uploading: '正在上传 {name}',
    uploadFailed: '上传失败：{message}',
    auditStarted: '已开始审核',
    auditFailed: '操作失败：{message}',
    deleted: '已删除',
    deleteConfirm: '确定删除这份文档？',
    unsupported: '只支持 PDF 和 Word(.docx) 文件',
    tooLarge: '单个文件不能超过 200 MiB',
    grades: 'A 级 {A} · B 级 {B} · C 级 {C}',
    progress: '审核中 · {progress}%',
    failedSummary: '审核失败',
    reportNotReady: '报告尚未生成，请先完成审核',
    timeFilter: '上传时间',
  },
  'en-US': {
    upload: 'Upload',
    search: 'Search document name',
    allStatus: 'All statuses',
    statusPending: 'Pending',
    statusRunning: 'Auditing',
    statusCompleted: 'Completed',
    statusFailed: 'Failed',
    colName: 'Document',
    colUploadedAt: 'Uploaded',
    colStatus: 'Status',
    colResult: 'Result',
    colActions: 'Actions',
    emptyTitle: 'No documents yet',
    emptyBody: 'Use “Upload” to start an audit.',
    count: '{count} document(s)',
    startAudit: 'Start audit',
    viewProgress: 'View progress',
    viewResult: 'View result',
    downloadReport: 'Download report',
    reaudit: 'Re-audit',
    retry: 'Retry',
    delete: 'Delete',
    noFindings: 'No findings',
    findings: '{total} finding(s) · {review} to review',
    uploadTitle: 'Upload documents',
    dropzone: 'Drop PDF / Word files here',
    dropzoneHint: 'or click to choose files (max 200 MiB each)',
    cancel: 'Cancel',
    confirmUpload: 'Upload',
    close: 'Close',
    openReport: 'Download report',
    colRule: 'Rule',
    colCheck: 'Check',
    colVerdict: 'Verdict',
    colPage: 'Page',
    colDetail: 'Issue and remediation',
    colEvidence: 'Evidence',
    evidenceMissing: 'None',
    verdictPass: 'Pass',
    verdictFail: 'Fail',
    verdictReview: 'Review',
    verdictNA: 'N/A',
    resultsLoading: 'Loading audit results…',
    resultsNotReady: 'Audit results are not ready',
    resultsOverview: 'Overall: {verdict} · Pass {pass} · Fail {fail} · Review {review} · N/A {na}',
    viewAudit: 'Audit',
    viewStandards: 'Standards',
    uploadStandard: 'Upload standard',
    standardHint: 'Upload rule/standard documents (PDF, Word, Markdown, txt). They are compiled into skill rule packs and enabled for everyone who can open this provider; the next audit uses them.',
    colStandardName: 'Standard',
    colStandardRules: 'Rules',
    colStandardStatus: 'Status',
    colStandardUploadedAt: 'Uploaded',
    standardCount: '{count} standard(s)',
    standardUploaded: 'Standard uploaded',
    standardDeleted: 'Standard deleted',
    standardDeleteConfirm: 'Delete this standard?',
    standardEmptyTitle: 'No standards yet',
    standardEmptyBody: 'Use “Upload standard” to add audit criteria.',
    statusCompiling: 'Compiling',
    statusActive: 'Active',
    statusCompileFailed: 'Compile failed',
    recompile: 'Recompile',
    recompileStarted: 'Recompiling',
    unsupportedStandard: 'Only PDF, Word, Markdown and txt rule documents are supported',
    download: 'Download',
    uploading: 'Uploading {name}',
    uploadFailed: 'Upload failed: {message}',
    auditStarted: 'Audit started',
    auditFailed: 'Action failed: {message}',
    deleted: 'Deleted',
    deleteConfirm: 'Delete this document?',
    unsupported: 'Only PDF and Word (.docx) files are supported',
    tooLarge: 'Each file must be at most 200 MiB',
    grades: 'A {A} · B {B} · C {C}',
    progress: 'Auditing · {progress}%',
    failedSummary: 'Audit failed',
    reportNotReady: 'The report is not ready yet. Finish the audit first.',
    timeFilter: 'Upload time',
  },
};

const state = {
  basePath: '',
  locale: 'zh-CN',
  items: [],
  standards: [],
  view: 'audit',
  filter: '',
  query: '',
  days: '',
  pendingFiles: [],
  pollTimer: null,
  standardsTimer: null,
  currentResultId: '',
  started: false,
};

const els = {};

function t(key, params = {}) {
  const table = MESSAGES[state.locale] || MESSAGES['zh-CN'];
  const template = table[key] || key;
  return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
}

function apiBase() {
  return `${state.basePath || ''}/api/providers/audit-report/default`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function notifyCore(message, level = 'info') {
  try {
    window.parent?.postMessage({ type: 'atlasclaw:toast', level, message }, window.location.origin);
  } catch (error) {
    console.warn('[audit-report] toast failed', error);
  }
}

function showToast(message, level = 'info') {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.dataset.level = level;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { els.toast.hidden = true; }, 3600);
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase()}${path}`, {
    credentials: 'same-origin',
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch (_) { payload = null; }
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : (detail?.message || `HTTP ${response.status}`);
    throw new Error(message);
  }
  return payload;
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(state.locale, {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function statusLabel(status) {
  return {
    pending: t('statusPending'),
    running: t('statusRunning'),
    completed: t('statusCompleted'),
    failed: t('statusFailed'),
  }[status] || status;
}

function resultText(document) {
  if (document.status === 'completed') {
    if (!document.findings_total) return t('noFindings');
    return t('findings', { total: document.findings_total, review: document.findings_review });
  }
  if (document.status === 'running') {
    return t('progress', { progress: document.progress || 0 });
  }
  if (document.status === 'failed') return t('failedSummary');
  return '—';
}

function actionButtons(document) {
  const actions = document.actions || [];
  const buttons = [];
  const add = (action, label, style = '') => buttons.push(
    `<button type="button" class="action ${style}" data-action="${action}" data-id="${escapeHtml(document.id)}">${escapeHtml(label)}</button>`
  );
  if (actions.includes('start_audit')) add('audit', t('startAudit'));
  if (actions.includes('view_progress')) add('result', t('viewProgress'));
  if (actions.includes('view_result')) add('result', t('viewResult'));
  if (actions.includes('retry') || actions.includes('reaudit')) add('audit', t('retry'));
  if (actions.includes('delete')) add('delete', t('delete'), 'danger');
  return buttons.join('');
}

function filteredItems() {
  const query = state.query.trim().toLowerCase();
  const now = Date.now();
  return state.items.filter(document => {
    if (state.filter && document.status !== state.filter) return false
    if (query) {
      const haystack = `${document.file_name || ''} ${document.report_no || ''}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (state.days) {
      const created = Date.parse(document.created_at || '');
      if (Number.isFinite(created) && now - created > Number(state.days) * 86400000) return false;
    }
    return true;
  });
}

function renderTable() {
  const items = filteredItems();
  els.rows.innerHTML = items.map(document => {
    const extension = (document.file_name || '').toLowerCase().endsWith('.docx') ? 'DOCX' : 'PDF';
    return `
      <tr>
        <td class="name-cell">
          <span class="file-badge ${extension.toLowerCase()}">${extension}</span>
          <span class="file-name" title="${escapeHtml(document.file_name)}">${escapeHtml(document.file_name)}</span>
        </td>
        <td>${escapeHtml(formatTime(document.created_at))}</td>
        <td><span class="status status-${escapeHtml(document.status)}">${escapeHtml(statusLabel(document.status))}</span></td>
        <td class="result-cell">${escapeHtml(resultText(document))}</td>
        <td class="actions-cell"><div class="row-actions">${actionButtons(document)}</div></td>
      </tr>
    `;
  }).join('');
  els.emptyState.hidden = items.length > 0;
  els.table.hidden = items.length === 0;
  els.count.textContent = t('count', { count: items.length });
}

async function loadDocuments() {
  window.clearTimeout(state.pollTimer);
  try {
    const payload = await api('/documents?page_size=100');
    state.items = payload.items || [];
    renderTable();
    if (state.items.some(item => item.status === 'running')) {
      state.pollTimer = window.setTimeout(loadDocuments, 3000);
    }
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function standardStatusLabel(standard) {
  if (standard.status === 'compiling') return t('statusCompiling');
  if (standard.status === 'failed') return t('statusCompileFailed');
  return t('statusActive');
}

function standardBadge(standard) {
  if (standard.status === 'compiling') return 'pending';
  if (standard.status === 'failed') return 'failed';
  return 'completed';
}

function renderStandards() {
  els.standardRows.innerHTML = state.standards.map(standard => {
    const badge = standardBadge(standard);
    const title = standard.error_message
      ? ` title="${escapeHtml(standard.error_message)}"`
      : '';
    const rules = standard.rules ? escapeHtml(String(standard.rules)) : '—';
    const recompile = standard.status === 'compiling'
      ? ''
      : `<button type="button" class="action" data-standard-action="recompile" data-id="${escapeHtml(standard.id)}">${escapeHtml(t('recompile'))}</button>`;
    return `
    <tr>
      <td class="name-cell">
        <span class="file-badge ${standard.extension === '.docx' ? 'docx' : (standard.extension === '.pdf' ? 'pdf' : 'md')}">${escapeHtml((standard.extension || '.pdf').replace('.', '').toUpperCase())}</span>
        <span class="file-name" title="${escapeHtml(standard.file_name)}">${escapeHtml(standard.file_name)}</span>
      </td>
      <td>${rules}</td>
      <td><span class="status status-${badge}"${title}>${escapeHtml(standardStatusLabel(standard))}</span></td>
      <td>${escapeHtml(formatTime(standard.created_at))}</td>
      <td class="actions-cell"><div class="row-actions">
        <button type="button" class="action" data-standard-action="download" data-id="${escapeHtml(standard.id)}">${escapeHtml(t('download'))}</button>
        ${recompile}
        <button type="button" class="action danger" data-standard-action="delete" data-id="${escapeHtml(standard.id)}">${escapeHtml(t('delete'))}</button>
      </div></td>
    </tr>
  `;
  }).join('');
  els.standardEmpty.hidden = state.standards.length > 0;
  els.standardTable.hidden = state.standards.length === 0;
  els.standardCount.textContent = t('standardCount', { count: state.standards.length });
}

async function loadStandards() {
  window.clearTimeout(state.standardsTimer);
  try {
    const payload = await api('/standards');
    state.standards = payload.items || [];
    renderStandards();
    if (state.standards.some(item => item.status === 'compiling')) {
      state.standardsTimer = window.setTimeout(loadStandards, 4000);
    }
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function uploadStandardFiles(fileList) {
  const allowed = ['.pdf', '.docx', '.md', '.txt'];
  const files = Array.from(fileList || []).filter(file => {
    const name = String(file.name || '').toLowerCase();
    if (!allowed.some(extension => name.endsWith(extension))) {
      showToast(t('unsupportedStandard'), 'error');
      return false;
    }
    if (file.size > 200 * 1024 * 1024) {
      showToast(t('tooLarge'), 'error');
      return false;
    }
    return true;
  });
  for (const file of files) {
    const body = new FormData();
    body.append('file', file);
    try {
      await api('/standards', { method: 'POST', body });
      showToast(t('standardUploaded'), 'success');
    } catch (error) {
      showToast(t('uploadFailed', { message: error.message }), 'error');
    }
  }
  await loadStandards();
}

async function recompileStandard(standardId) {
  try {
    await api(`/standards/${encodeURIComponent(standardId)}/recompile`, { method: 'POST' });
    showToast(t('recompileStarted'), 'success');
    await loadStandards();
  } catch (error) {
    showToast(t('auditFailed', { message: error.message }), 'error');
  }
}

async function deleteStandard(standardId) {
  if (!window.confirm(t('standardDeleteConfirm'))) return;
  try {
    await api(`/standards/${encodeURIComponent(standardId)}`, { method: 'DELETE' });
    showToast(t('standardDeleted'), 'success');
    await loadStandards();
  } catch (error) {
    showToast(t('auditFailed', { message: error.message }), 'error');
  }
}

function downloadStandard(standardId) {
  const link = window.document.createElement('a');
  link.href = `${apiBase()}/standards/${encodeURIComponent(standardId)}/file`;
  link.rel = 'noopener';
  window.document.body.appendChild(link);
  link.click();
  link.remove();
}

function switchView(view) {
  state.view = view;
  els.auditView.hidden = view !== 'audit';
  els.standardsView.hidden = view !== 'standards';
  els.viewTabs.forEach(tab => {
    const active = tab.dataset.view === view;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  if (view === 'standards') loadStandards();
}

async function startAudit(documentId) {
  try {
    await api(`/documents/${encodeURIComponent(documentId)}/audit`, { method: 'POST' });
    showToast(t('auditStarted'), 'success');
    notifyCore(t('auditStarted'), 'success');
    await loadDocuments();
  } catch (error) {
    showToast(t('auditFailed', { message: error.message }), 'error');
  }
}

async function deleteDocument(documentId) {
  if (!window.confirm(t('deleteConfirm'))) return;
  try {
    await api(`/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
    showToast(t('deleted'), 'success');
    await loadDocuments();
  } catch (error) {
    showToast(t('auditFailed', { message: error.message }), 'error');
  }
}

function reportUrl(documentId, download = false) {
  const suffix = download ? '/report/download' : '/report';
  return `${apiBase()}/documents/${encodeURIComponent(documentId)}${suffix}`;
}

function downloadReport(documentId) {
  const document = state.items.find(item => item.id === documentId);
  if (!document || document.status !== 'completed' || !document.report_available) {
    showToast(t('reportNotReady'), 'error');
    return;
  }
  const link = window.document.createElement('a');
  link.href = reportUrl(documentId, true);
  link.rel = 'noopener';
  window.document.body.appendChild(link);
  link.click();
  link.remove();
}

function verdictLabel(verdict) {
  return {
    PASS: t('verdictPass'),
    FAIL: t('verdictFail'),
    REVIEW: t('verdictReview'),
    NA: t('verdictNA'),
  }[verdict] || verdict;
}

function evidenceUrl(documentId, image) {
  if (!image) return '';
  const name = String(image).split('/').pop();
  return `${apiBase()}/documents/${encodeURIComponent(documentId)}/evidence/${encodeURIComponent(name)}`;
}

function renderResults(payload) {
  const counts = payload.counts || {};
  const rows = (payload.results || []).map(item => {
    const verdict = String(item.verdict || '').toUpperCase();
    const detail = [item.problem, item.suggestion].filter(Boolean).join(' ／ ');
    const imageUrl = evidenceUrl(payload.document_id, item.image);
    const evidenceCell = imageUrl
      ? `<a href="${imageUrl}" target="_blank" rel="noopener"><img class="evidence-thumb" src="${imageUrl}" alt="${escapeHtml(t('colEvidence'))}"></a>`
      : escapeHtml(t('evidenceMissing'));
    return `
      <tr>
        <td class="rule-cell">${escapeHtml(item.rule)}</td>
        <td>${escapeHtml(item.title || '')}</td>
        <td><span class="verdict verdict-${verdict.toLowerCase()}">${escapeHtml(verdictLabel(verdict))}</span></td>
        <td>${item.page ? `第 ${escapeHtml(String(item.page))} 页` : '—'}</td>
        <td class="detail-cell">${escapeHtml(detail || '—')}</td>
        <td class="evidence-cell">${evidenceCell}</td>
      </tr>
    `;
  }).join('');
  const overview = t('resultsOverview', {
    verdict: payload.verdict || '',
    pass: counts.PASS || 0,
    fail: counts.FAIL || 0,
    review: counts.REVIEW || 0,
    na: counts.NA || 0,
  });
  return `
    <p class="result-overview ${payload.verdict === '通过' ? 'ok' : 'bad'}">${escapeHtml(overview)}</p>
    <table class="result-table">
      <thead>
        <tr>
          <th>${escapeHtml(t('colRule'))}</th>
          <th>${escapeHtml(t('colCheck'))}</th>
          <th>${escapeHtml(t('colVerdict'))}</th>
          <th>${escapeHtml(t('colPage'))}</th>
          <th>${escapeHtml(t('colDetail'))}</th>
          <th>${escapeHtml(t('colEvidence'))}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function showResult(documentId) {
  const document = state.items.find(item => item.id === documentId);
  if (!document) return;
  state.currentResultId = documentId;
  els.resultTitle.textContent = document.file_name;
  const grades = document.grade_summary || {};
  els.resultSummary.innerHTML = `
    <p class="result-line">${escapeHtml(resultText(document))}</p>
    <p class="result-line">${escapeHtml(t('grades', {
      A: grades.A || 0, B: grades.B || 0, C: grades.C || 0,
    }))}</p>
    ${document.status === 'running' ? `<div class="progress-bar"><span style="width:${Number(document.progress) || 0}%"></span></div>` : ''}
  `;
  els.openReport.hidden = document.status !== 'completed' || !document.report_available;
  els.resultModal.hidden = false;
  if (document.status !== 'completed') {
    els.resultBody.innerHTML = `<p class="result-line">${escapeHtml(t('resultsNotReady'))}</p>`;
    return;
  }
  els.resultBody.innerHTML = `<p class="result-line">${escapeHtml(t('resultsLoading'))}</p>`;
  try {
    const payload = await api(`/documents/${encodeURIComponent(documentId)}/results`);
    els.resultBody.innerHTML = renderResults(payload);
  } catch (error) {
    els.resultBody.innerHTML = `<p class="result-line">${escapeHtml(error.message)}</p>`;
  }
}

function openUploadModal() {
  state.pendingFiles = [];
  renderUploadList();
  els.uploadModal.hidden = false;
}

function renderUploadList() {
  els.uploadList.innerHTML = state.pendingFiles.map(file => (
    `<li><span>${escapeHtml(file.name)}</span><small>${(file.size / 1024 / 1024).toFixed(1)} MiB</small></li>`
  )).join('');
  els.confirmUpload.disabled = state.pendingFiles.length === 0;
}

function addFiles(fileList) {
  for (const file of Array.from(fileList || [])) {
    const name = String(file.name || '').toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
      showToast(t('unsupported'), 'error');
      continue;
    }
    if (file.size > 200 * 1024 * 1024) {
      showToast(t('tooLarge'), 'error');
      continue;
    }
    state.pendingFiles.push(file);
  }
  renderUploadList();
}

async function uploadPending() {
  const files = [...state.pendingFiles];
  if (!files.length) return;
  els.confirmUpload.disabled = true;
  for (const file of files) {
    showToast(t('uploading', { name: file.name }), 'info');
    const form = new FormData();
    form.append('file', file);
    try {
      await fetch(`${apiBase()}/documents`, {
        method: 'POST', body: form, credentials: 'same-origin',
      }).then(async response => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          const detail = payload?.detail;
          throw new Error(typeof detail === 'string' ? detail : (detail?.message || `HTTP ${response.status}`));
        }
      });
    } catch (error) {
      showToast(t('uploadFailed', { message: error.message }), 'error');
      els.confirmUpload.disabled = false;
      return;
    }
  }
  state.pendingFiles = [];
  els.uploadModal.hidden = true;
  await loadDocuments();
}

function bindEvents() {
  els.uploadButton.addEventListener('click', openUploadModal);
  els.cancelUpload.addEventListener('click', () => { els.uploadModal.hidden = true; });
  els.confirmUpload.addEventListener('click', uploadPending);
  els.fileInput.addEventListener('change', event => addFiles(event.target.files));
  els.dropzone.addEventListener('click', () => els.fileInput.click());
  els.dropzone.addEventListener('dragover', event => {
    event.preventDefault();
    els.dropzone.classList.add('dragging');
  });
  els.dropzone.addEventListener('dragleave', () => els.dropzone.classList.remove('dragging'));
  els.dropzone.addEventListener('drop', event => {
    event.preventDefault();
    els.dropzone.classList.remove('dragging');
    addFiles(event.dataTransfer?.files);
  });
  els.searchInput.addEventListener('input', () => {
    state.query = els.searchInput.value;
    renderTable();
  });
  els.statusFilter.addEventListener('change', () => {
    state.filter = els.statusFilter.value;
    renderTable();
  });
  els.timeFilter.addEventListener('change', () => {
    state.days = els.timeFilter.value;
    renderTable();
  });
  els.rows.addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const { action, id } = button.dataset;
    if (action === 'audit') startAudit(id);
    else if (action === 'delete') deleteDocument(id);
    else if (action === 'result') showResult(id);
    else if (action === 'download') downloadReport(id);
  });
  els.closeResult.addEventListener('click', () => { els.resultModal.hidden = true; });
  els.openReport.addEventListener('click', () => {
    if (state.currentResultId) downloadReport(state.currentResultId);
  });
  els.viewTabs.forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });
  els.standardUploadButton.addEventListener('click', () => els.standardInput.click());
  els.standardInput.addEventListener('change', async () => {
    await uploadStandardFiles(els.standardInput.files);
    els.standardInput.value = '';
  });
  els.standardRows.addEventListener('click', event => {
    const button = event.target.closest('[data-standard-action]');
    if (!button) return;
    const { standardAction, id } = button.dataset;
    if (standardAction === 'download') downloadStandard(id);
    else if (standardAction === 'recompile') recompileStandard(id);
    else if (standardAction === 'delete') deleteStandard(id);
  });
  window.addEventListener('beforeunload', () => {
    window.clearTimeout(state.pollTimer);
    window.clearTimeout(state.standardsTimer);
  });
}

function applyLocale() {
  els.uploadButton.querySelector('span:last-child').textContent = t('upload');
  els.searchInput.placeholder = t('search');
  els.statusFilter.options[0].textContent = t('allStatus');
  els.statusFilter.options[1].textContent = t('statusPending');
  els.statusFilter.options[2].textContent = t('statusRunning');
  els.statusFilter.options[3].textContent = t('statusCompleted');
  els.statusFilter.options[4].textContent = t('statusFailed');
  els.timeFilter.options[0].textContent = t('timeFilter');
  document.getElementById('thName').textContent = t('colName');
  document.getElementById('thUploadedAt').textContent = t('colUploadedAt');
  document.getElementById('thStatus').textContent = t('colStatus');
  document.getElementById('thResult').textContent = t('colResult');
  document.getElementById('thActions').textContent = t('colActions');
  els.emptyState.querySelector('h2').textContent = t('emptyTitle');
  els.emptyState.querySelector('p').textContent = t('emptyBody');
  els.cancelUpload.textContent = t('cancel');
  els.confirmUpload.textContent = t('confirmUpload');
  els.closeResult.textContent = t('close');
  els.openReport.textContent = t('openReport');
  document.getElementById('uploadTitle').textContent = t('uploadTitle');
  els.dropzone.querySelector('strong').textContent = t('dropzone');
  els.dropzone.querySelector('span').textContent = t('dropzoneHint');
  els.standardUploadButton.querySelector('span:last-child').textContent = t('uploadStandard');
  document.querySelector('.standards-hint').textContent = t('standardHint');
  document.getElementById('thStandardName').textContent = t('colStandardName');
  document.getElementById('thStandardRules').textContent = t('colStandardRules');
  document.getElementById('thStandardStatus').textContent = t('colStandardStatus');
  document.getElementById('thStandardUploadedAt').textContent = t('colStandardUploadedAt');
  document.getElementById('thStandardActions').textContent = t('colActions');
  els.standardEmpty.querySelector('h2').textContent = t('standardEmptyTitle');
  els.standardEmpty.querySelector('p').textContent = t('standardEmptyBody');
  els.viewTabs.forEach(tab => { tab.textContent = t(tab.dataset.view === 'standards' ? 'viewStandards' : 'viewAudit'); });
  renderTable();
  renderStandards();
}

function start() {
  if (state.started) return;
  state.started = true;
  Object.assign(els, {
    rows: document.getElementById('documentRows'),
    table: document.querySelector('.document-table'),
    emptyState: document.getElementById('emptyState'),
    count: document.getElementById('documentCount'),
    uploadButton: document.getElementById('uploadButton'),
    searchInput: document.getElementById('searchInput'),
    statusFilter: document.getElementById('statusFilter'),
    timeFilter: document.getElementById('timeFilter'),
    uploadModal: document.getElementById('uploadModal'),
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    uploadList: document.getElementById('uploadList'),
    cancelUpload: document.getElementById('cancelUpload'),
    confirmUpload: document.getElementById('confirmUpload'),
    resultModal: document.getElementById('resultModal'),
    resultTitle: document.getElementById('resultTitle'),
    resultSummary: document.getElementById('resultSummary'),
    resultBody: document.getElementById('resultBody'),
    closeResult: document.getElementById('closeResult'),
    openReport: document.getElementById('openReport'),
    viewTabs: [...document.querySelectorAll('.view-tab')],
    auditView: document.getElementById('auditView'),
    standardsView: document.getElementById('standardsView'),
    standardUploadButton: document.getElementById('standardUploadButton'),
    standardInput: document.getElementById('standardInput'),
    standardRows: document.getElementById('standardRows'),
    standardTable: document.querySelector('.standards-table'),
    standardEmpty: document.getElementById('standardEmpty'),
    standardCount: document.getElementById('standardCount'),
    toast: document.getElementById('toast'),
  });
  bindEvents();
  applyLocale();
  switchView('audit');
  loadDocuments();
}

window.addEventListener('message', event => {
  if (event.origin !== window.location.origin) return;
  const data = event.data;
  if (!data || data.type !== 'atlasclaw:init') return;
  state.basePath = String(data.basePath || '');
  state.locale = String(data.locale || 'zh-CN');
  document.documentElement.dataset.theme = data.theme || 'light';
  applyLocale();
  loadDocuments();
});

try {
  window.parent?.postMessage({ type: 'atlasclaw:ready', version: 1 }, window.location.origin);
} catch (error) {
  console.warn('[audit-report] ready signal failed', error);
}

start();
window.setTimeout(() => { if (!state.started) start(); }, 1500);
