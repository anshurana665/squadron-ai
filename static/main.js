// ─── AGENT COLOR MAP ───────────────────────────────────────────
const AGENT_COLORS = {
  manager:   { label: '#a29bfe', text: '#a29bfe' },
  developer: { label: '#fd7c6e', text: '#fd7c6e' },
  reviewer:  { label: '#55efc4', text: '#55efc4' },
  system:    { label: '#636e72', text: '#b2bec3' },
  batch:     { label: '#fdcb6e', text: '#fdcb6e' },
};

// ─── STATE ─────────────────────────────────────────────────────
let _currentFile = null;
let _currentJobId = null;
let _ws = null;
let _patchedCode = '';
let _filename = 'patched_code.py';

// ─── LANDING PAGE OBSERVERS ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Intersection observer for animate-in
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add('visible'); observer.unobserve(e.target); }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.animate-in').forEach(el => {
    if (!el.classList.contains('visible')) observer.observe(el);
  });

  // Animate score bars on scroll
  const scoreObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.querySelectorAll('.score-bar-fill').forEach(bar => {
          const w = bar.style.width; bar.style.width = '0';
          setTimeout(() => { bar.style.width = w; }, 100);
        });
        scoreObserver.unobserve(e.target);
      }
    });
  }, { threshold: 0.3 });
  const benchTable = document.querySelector('.bench-table-wrap');
  if (benchTable) scoreObserver.observe(benchTable);

  initAuditSection();
});

// ─── TOGGLE UI ─────────────────────────────────────────────────
function updateToggleUI(checkbox) {
  const knob = document.getElementById('toggle-knob');
  const bg   = document.getElementById('toggle-bg');
  if (!knob || !bg) return;
  if (checkbox.checked) {
    knob.style.transform = 'translateX(22px)';
    bg.style.background  = '#6C5CE7';
  } else {
    knob.style.transform = 'translateX(0)';
    bg.style.background  = '#d1c7ff';
  }
}

// ─── AUDIT SECTION INIT ────────────────────────────────────────
function initAuditSection() {
  const fileInput   = document.getElementById('audit-file-input');
  const browseBtn   = document.getElementById('audit-browse-btn');
  const dropZone    = document.getElementById('drop-zone');
  const submitBtn   = document.getElementById('audit-submit-btn');

  if (!fileInput) return;

  // Browse
  browseBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
  dropZone.addEventListener('click', () => fileInput.click());

  // Drag & Drop
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor  = '#6C5CE7';
    dropZone.style.background   = 'rgba(108,92,231,0.05)';
    dropZone.style.transform    = 'scale(0.99)';
  });
  dropZone.addEventListener('dragleave', () => { resetDropZone(); });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault(); resetDropZone();
    if (e.dataTransfer.files.length > 0) selectFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) selectFile(fileInput.files[0]);
  });

  submitBtn.addEventListener('click', startAudit);
}

function resetDropZone() {
  const dz = document.getElementById('drop-zone');
  if (!dz) return;
  dz.style.borderColor = 'rgba(108,92,231,0.3)';
  dz.style.background  = 'var(--bg)';
  dz.style.transform   = 'scale(1)';
}

function selectFile(file) {
  _currentFile = file;
  _filename = file.name.replace(/\.[^.]+$/, '_hardened') + (file.name.endsWith('.zip') ? '.zip' : '.py');

  // Show selected indicator
  const sel  = document.getElementById('audit-file-selected');
  const name = document.getElementById('audit-filename');
  const size = document.getElementById('audit-filesize');
  if (sel && name && size) {
    name.textContent = file.name;
    size.textContent = formatBytes(file.size);
    sel.style.display = 'flex';
  }

  // Enable submit
  const btn = document.getElementById('audit-submit-btn');
  if (btn) {
    btn.disabled        = false;
    btn.style.opacity   = '1';
    btn.style.cursor    = 'pointer';
  }
}

function formatBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}

// ─── START AUDIT ───────────────────────────────────────────────
async function startAudit() {
  if (!_currentFile) return;

  const issueDesc    = document.getElementById('audit-issue-desc')?.value || '';
  const secMode      = document.getElementById('audit-security-mode')?.checked || false;
  const submitBtn    = document.getElementById('audit-submit-btn');

  submitBtn.disabled      = true;
  submitBtn.textContent   = '⏳ Deploying Agents...';

  const formData = new FormData();
  formData.append('file', _currentFile);
  formData.append('issue_desc', issueDesc || 'Analyze for bugs and security vulnerabilities. Fix all issues.');
  formData.append('security_mode', String(secMode));

  try {
    const endpoint = _currentFile.name.endsWith('.zip') ? '/api/audit/zip' : '/api/audit/file';
    const resp = await fetch(endpoint, { method: 'POST', body: formData });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      termLog({ type: 'error', message: 'Upload failed: ' + err.detail });
      submitBtn.disabled    = false;
      submitBtn.textContent = '🚀 Deploy Security Squad';
      return;
    }

    const data = await resp.json();
    _currentJobId = data.job_id;

    // Show workspace
    document.getElementById('audit-upload').style.display    = 'none';
    document.getElementById('audit-workspace').style.display = 'block';
    document.getElementById('audit-terminal').innerHTML      = '';

    // Update terminal title
    const titleEl = document.getElementById('audit-terminal-title');
    if (titleEl) titleEl.textContent = `squadron.ai — ${_currentFile.name}`;

    connectWS(data.job_id);

  } catch (err) {
    termLog({ type: 'error', message: 'Network error: ' + err.message });
    submitBtn.disabled    = false;
    submitBtn.textContent = '🚀 Deploy Security Squad';
  }
}

// ─── WEBSOCKET ─────────────────────────────────────────────────
function connectWS(jobId) {
  termLog({ agent: 'system', message: `Connecting to stream ${jobId.slice(0, 8)}...` });

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  _ws = new WebSocket(`${proto}//${location.host}/ws/${jobId}`);

  _ws.onopen = () => termLog({ agent: 'system', message: 'Stream online. Awaiting agents...' });

  _ws.onmessage = (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }

    if (data.type === 'ping') return;

    if (data.type === 'evpc_result' && data.data?.score != null) {
      animateScore(parseFloat(data.data.score));
    }

    termLog(data);

    if (data.type === 'complete' || data.type === 'error') {
      const resetBtn = document.getElementById('audit-reset-btn');
      if (resetBtn) resetBtn.style.display = 'inline-block';
      _ws?.close();
      fetchResult(jobId);
    }
  };

  _ws.onerror = () => termLog({ type: 'error', agent: 'system', message: 'WebSocket error.' });
  _ws.onclose = () => {
    termLog({ agent: 'system', message: 'Stream closed.' });
    fetchResult(jobId);
  };
}

// ─── TERMINAL LOGGER ───────────────────────────────────────────
function termLog(event) {
  const terminal = document.getElementById('audit-terminal');
  if (!terminal) return;

  const msg = (event.message || '').trim();
  if (!msg) return;

  const agentKey  = (event.agent || 'system').toLowerCase();
  const colors    = AGENT_COLORS[agentKey] || AGENT_COLORS.system;

  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:0.5rem;align-items:flex-start;margin-bottom:0.15rem;';

  if (event.agent) {
    const label = document.createElement('span');
    label.style.cssText = `color:${colors.label};font-weight:600;flex-shrink:0;min-width:110px;`;
    label.textContent = `[${event.agent.toUpperCase()}]`;
    row.appendChild(label);
  }

  const textNode = document.createElement('span');
  textNode.style.color = event.type === 'error' ? '#fd7c6e'
                       : event.type === 'complete' ? '#55efc4'
                       : colors.text;
  row.appendChild(textNode);

  // Cursor blink
  const cursor = document.createElement('span');
  cursor.style.cssText = 'display:inline-block;width:2px;height:1em;background:#a29bfe;vertical-align:middle;animation:blink 1s step-end infinite;';
  row.appendChild(cursor);

  terminal.appendChild(row);

  // Typewriter
  let i = 0;
  const speed = msg.length > 60 ? 3 : 12;
  function type() {
    if (i < msg.length) {
      textNode.textContent += msg.charAt(i++);
      terminal.scrollTop = terminal.scrollHeight;
      setTimeout(type, speed);
    } else {
      cursor.remove();
    }
  }
  type();
}

// ─── EVPC SCORE ANIMATION ──────────────────────────────────────
function animateScore(score) {
  const scoreNum = document.getElementById('score-num');
  const scoreArc = document.getElementById('score-arc');
  const verdict  = document.getElementById('score-verdict');

  if (!scoreNum || !scoreArc) return;

  const circumference = 276.5;
  const offset = circumference - (score * circumference);
  scoreArc.style.strokeDashoffset = offset;

  // Color
  let color, verdictText;
  if (score >= 0.8) {
    color = '#00b894'; verdictText = '✅ Production Ready';
  } else if (score >= 0.5) {
    color = '#fdcb6e'; verdictText = '⚠️ Needs Review';
  } else {
    color = '#fd7c6e'; verdictText = '🔴 High Risk';
  }
  scoreArc.style.stroke = color;
  if (scoreNum) scoreNum.style.color = color;
  if (verdict)  verdict.textContent  = verdictText;

  // Animate counter
  let current = 0;
  const target = Math.round(score * 100);
  const step = () => {
    if (current < target) {
      current++;
      scoreNum.textContent = current + '%';
      requestAnimationFrame(step);
    } else {
      scoreNum.textContent = target + '%';
    }
  };
  requestAnimationFrame(step);
}

// ─── FETCH RESULT ──────────────────────────────────────────────
async function fetchResult(jobId) {
  try {
    const resp = await fetch(`/api/result/${jobId}`);
    if (!resp.ok) return;
    const result = await resp.json();

    const codeEl = document.getElementById('audit-code-output');
    if (codeEl) {
      const ext = (_currentFile?.name || '').split('.').pop().toLowerCase();
      const langMap = { js: 'javascript', html: 'xml', css: 'css', cpp: 'cpp', java: 'java', py: 'python' };
      const lang = langMap[ext] || 'python';

      const code = result.fixed_code
        || (result.original_code && !result.changed ? '# No vulnerabilities found. Code is clean.\n\n' + result.original_code : null)
        || '# Batch audit complete.';

      _patchedCode = code;

      // CRITICAL: strip old hljs classes, set new lang, then set content, then highlight
      codeEl.removeAttribute('data-highlighted');
      codeEl.className = `language-${lang}`;
      codeEl.textContent = code;

      if (window.hljs) {
        hljs.highlightElement(codeEl);
      }
    }

    if (result.evpc_score != null) {
      const scoreNum = document.getElementById('score-num');
      if (scoreNum && (scoreNum.textContent === '--' || scoreNum.textContent === '')) {
        animateScore(parseFloat(result.evpc_score));
      }
    }
  } catch (err) {
    console.error('fetchResult error:', err);
  }
}

// ─── COPY & DOWNLOAD ───────────────────────────────────────────
function copyCode() {
  const code = document.getElementById('audit-code-output')?.textContent || '';
  navigator.clipboard.writeText(code).then(() => {
    const btn = document.querySelector('[onclick="copyCode()"]');
    if (btn) { btn.textContent = '✅ Copied!'; setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000); }
  });
}

function downloadCode() {
  const code = document.getElementById('audit-code-output')?.textContent || '';
  const blob = new Blob([code], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = _filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ─── RESET ─────────────────────────────────────────────────────
function resetAudit() {
  _currentFile  = null;
  _currentJobId = null;
  _patchedCode  = '';
  if (_ws) { _ws.close(); _ws = null; }

  const upload    = document.getElementById('audit-upload');
  const workspace = document.getElementById('audit-workspace');
  const fileInput = document.getElementById('audit-file-input');
  const fileSel   = document.getElementById('audit-file-selected');
  const submitBtn = document.getElementById('audit-submit-btn');
  const scoreNum  = document.getElementById('score-num');
  const scoreArc  = document.getElementById('score-arc');
  const verdict   = document.getElementById('score-verdict');
  const resetBtn  = document.getElementById('audit-reset-btn');
  const terminal  = document.getElementById('audit-terminal');
  const codeEl    = document.getElementById('audit-code-output');

  if (upload)    upload.style.display    = 'block';
  if (workspace) workspace.style.display = 'none';
  if (fileInput) fileInput.value         = '';
  if (fileSel)   fileSel.style.display   = 'none';

  if (submitBtn) {
    submitBtn.disabled      = true;
    submitBtn.style.opacity = '0.45';
    submitBtn.style.cursor  = 'not-allowed';
    submitBtn.textContent   = '🚀 Deploy Security Squad';
  }
  if (scoreNum) { scoreNum.textContent = '--'; scoreNum.style.color = 'var(--primary)'; }
  if (scoreArc) { scoreArc.style.strokeDashoffset = '276.5'; scoreArc.style.stroke = '#6C5CE7'; }
  if (verdict)  verdict.textContent   = 'Awaiting results...';
  if (resetBtn) resetBtn.style.display = 'none';
  if (terminal) terminal.innerHTML    = '<div style="color:#636e72;">Waiting for file upload...</div>';
  if (codeEl)   { codeEl.textContent  = '# Waiting for Reviewer Agent to finalize patch...'; codeEl.className = 'language-python'; }

  // Scroll to audit section
  document.getElementById('audit')?.scrollIntoView({ behavior: 'smooth' });
}
