/* ══════════════════════════════════════════════════════════
   OpenSquad AI — app.js
   Particles · Nav · WebSocket · Drag&Drop · Diff Viewer
   ══════════════════════════════════════════════════════════ */

const API_BASE = "http://localhost:8000";
const WS_BASE  = "ws://localhost:8000";

/* ══════════════════════════════════════════════════════════
   1. PARTICLE BACKGROUND (3D star field + connections)
   ══════════════════════════════════════════════════════════ */
function initParticles(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  let W = canvas.width  = window.innerWidth;
  let H = canvas.height = window.innerHeight;

  const COUNT = 80;
  const particles = Array.from({ length: COUNT }, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    z: Math.random() * 1000,
    vx: (Math.random() - 0.5) * 0.3,
    vy: (Math.random() - 0.5) * 0.3,
    vz: -0.5 - Math.random() * 0.5,
    r: Math.random() * 2 + 0.5,
  }));

  let mouseX = W / 2, mouseY = H / 2;
  document.addEventListener("mousemove", e => { mouseX = e.clientX; mouseY = e.clientY; });

  window.addEventListener("resize", () => {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  });

  function project(p) {
    const fov = 500;
    const scale = fov / (fov + p.z);
    return {
      x: (p.x - W / 2) * scale + W / 2,
      y: (p.y - H / 2) * scale + H / 2,
      scale,
    };
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // Subtle grid
    ctx.strokeStyle = "rgba(88,166,255,0.03)";
    ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 80) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y < H; y += 80) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    // Update & draw particles
    for (const p of particles) {
      p.x += p.vx + (mouseX - W / 2) * 0.00008;
      p.y += p.vy + (mouseY - H / 2) * 0.00008;
      p.z += p.vz;

      if (p.z < 1)   p.z = 1000;
      if (p.x < 0)   p.x = W;
      if (p.x > W)   p.x = 0;
      if (p.y < 0)   p.y = H;
      if (p.y > H)   p.y = 0;

      const { x, y, scale } = project(p);
      const alpha = Math.min(1, scale * 1.5);
      const radius = p.r * scale;

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(88,166,255,${alpha * 0.7})`;
      ctx.fill();
    }

    // Draw connections between close particles
    for (let i = 0; i < particles.length; i++) {
      const a = project(particles[i]);
      for (let j = i + 1; j < particles.length; j++) {
        const b = project(particles[j]);
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 80) {
          const alpha = (1 - dist / 80) * 0.15;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(88,166,255,${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(draw);
  }

  draw();
}

/* ══════════════════════════════════════════════════════════
   2. NAV SCROLL EFFECT
   ══════════════════════════════════════════════════════════ */
function initNav() {
  const nav = document.getElementById("nav");
  if (!nav) return;
  window.addEventListener("scroll", () => {
    nav.classList.toggle("scrolled", window.scrollY > 20);
  });
}

/* ══════════════════════════════════════════════════════════
   3. AUDIT DASHBOARD
   ══════════════════════════════════════════════════════════ */
function initAuditDashboard() {
  /* ── State ── */
  let currentFile   = null;
  let currentMode   = "file";   // "file" | "zip"
  let jobId         = null;
  let ws            = null;
  let elapsedTimer  = null;
  let elapsedSecs   = 0;
  let auditResult   = null;

  /* ── DOM refs ── */
  const uploadZone     = document.getElementById("upload-zone");
  const fileInput      = document.getElementById("file-input");
  const fileInfo       = document.getElementById("file-info");
  const fileInfoName   = document.getElementById("file-info-name");
  const fileInfoSize   = document.getElementById("file-info-size");
  const fileClear      = document.getElementById("file-clear");
  const uploadSub      = document.getElementById("upload-sub");
  const runBtn         = document.getElementById("run-btn");
  const issueDesc      = document.getElementById("issue-desc");
  const securityMode   = document.getElementById("security-mode");
  const showThoughts   = document.getElementById("show-thoughts");
  const emptyState     = document.getElementById("empty-state");
  const liveLog        = document.getElementById("live-log");
  const liveLogBody    = document.getElementById("live-log-body");
  const liveElapsed    = document.getElementById("live-elapsed");
  const resultStats    = document.getElementById("result-stats");
  const diffContainer  = document.getElementById("diff-container");
  const diffBody       = document.getElementById("diff-body");
  const resultActions  = document.getElementById("result-actions");
  const btnDownload    = document.getElementById("btn-download");
  const btnReport      = document.getElementById("btn-report");
  const btnReset       = document.getElementById("btn-reset");
  const psTabs         = document.querySelectorAll(".pipeline-step");
  const modeTabs       = document.querySelectorAll(".mode-tab");
  const diffTabs       = document.querySelectorAll(".diff-tab");

  /* ── Mode tabs ── */
  modeTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      modeTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentMode = tab.dataset.mode;
      if (currentMode === "zip") {
        fileInput.accept = ".zip";
        uploadSub.textContent = "Supports .zip archives";
      } else {
        fileInput.accept = ".py,.js,.html,.css,.cpp,.java";
        uploadSub.textContent = "Supports .py .js .html .css .cpp .java";
      }
      clearFile();
    });
  });

  /* ── Drag & Drop ── */
  uploadZone.addEventListener("dragover", e => {
    e.preventDefault();
    uploadZone.classList.add("dragover");
  });
  uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("dragover");
  });
  uploadZone.addEventListener("drop", e => {
    e.preventDefault();
    uploadZone.classList.remove("dragover");
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });
  uploadZone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
  });

  fileClear.addEventListener("click", clearFile);

  function setFile(f) {
    currentFile = f;
    fileInfoName.textContent = f.name;
    fileInfoSize.textContent = formatBytes(f.size);
    fileInfo.classList.remove("hidden");
    uploadZone.style.display = "none";
    runBtn.disabled = false;
  }

  function clearFile() {
    currentFile = null;
    fileInfo.classList.add("hidden");
    uploadZone.style.display = "";
    runBtn.disabled = true;
    fileInput.value = "";
  }

  function formatBytes(b) {
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
    return (b / (1024 * 1024)).toFixed(1) + " MB";
  }

  /* ── Run audit ── */
  runBtn.addEventListener("click", startAudit);

  async function startAudit() {
    if (!currentFile) return;

    resetResults();
    show(liveLog);
    hide(emptyState);
    runBtn.disabled = true;
    runBtn.textContent = "Running...";

    // Start elapsed timer
    elapsedSecs = 0;
    liveElapsed.textContent = "0s";
    elapsedTimer = setInterval(() => {
      elapsedSecs++;
      liveElapsed.textContent = elapsedSecs + "s";
    }, 1000);

    // Build form data
    const form = new FormData();
    form.append("file", currentFile);
    form.append("issue_desc", issueDesc.value);
    form.append("security_mode", securityMode.checked);

    const endpoint = currentMode === "zip" ? "/api/audit/zip" : "/api/audit/file";

    try {
      const res = await fetch(API_BASE + endpoint, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "API error");
      }
      const data = await res.json();
      jobId = data.job_id;
      connectWebSocket(jobId);
    } catch (e) {
      appendLog({ type: "error", message: "Failed to start audit: " + e.message });
      runBtn.disabled = false;
      runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Audit';
      clearInterval(elapsedTimer);
    }
  }

  /* ── WebSocket ── */
  function connectWebSocket(id) {
    ws = new WebSocket(`${WS_BASE}/ws/${id}`);

    ws.onopen = () => {
      appendLog({ type: "agent_start", agent: "system", message: "Connected to agent pipeline..." });
    };

    ws.onmessage = e => {
      let event;
      try { event = JSON.parse(e.data); } catch { return; }
      if (event.type === "ping") return;

      if (showThoughts.checked || event.type !== "agent_thought") {
        appendLog(event);
      }

      updatePipelineStep(event);

      if (event.type === "complete") {
        clearInterval(elapsedTimer);
        ws.close();
        fetchResult(id);
      }
    };

    ws.onerror = () => {
      appendLog({ type: "error", message: "WebSocket error. Retrying via polling..." });
      pollForResult(id);
    };

    ws.onclose = () => {};
  }

  /* ── Poll fallback ── */
  async function pollForResult(id) {
    for (let i = 0; i < 60; i++) {
      await sleep(3000);
      try {
        const res = await fetch(`${API_BASE}/api/result/${id}`);
        if (!res.ok) continue;
        const data = await res.json();
        if (data.success !== undefined) {
          displayResult(data);
          return;
        }
      } catch {}
    }
    appendLog({ type: "error", message: "Timed out waiting for result." });
  }

  async function fetchResult(id) {
    try {
      const res = await fetch(`${API_BASE}/api/result/${id}`);
      const data = await res.json();
      displayResult(data);
    } catch (e) {
      appendLog({ type: "error", message: "Failed to fetch result: " + e.message });
    }
  }

  /* ── Display result ── */
  function displayResult(data) {
    auditResult = data;

    // Stat cards
    const scStatus = document.querySelector("#sc-status .sc-value");
    const scVulns  = document.querySelector("#sc-vulns .sc-value");
    const scEvpc   = document.querySelector("#sc-evpc .sc-value");

    if (data.changed) {
      scStatus.textContent = "Patched";
      scStatus.style.color = "var(--green)";
    } else {
      scStatus.textContent = "No Change";
      scStatus.style.color = "var(--red)";
    }

    const nVulns = Array.isArray(data.vulnerabilities) ? data.vulnerabilities.length : "—";
    scVulns.textContent = nVulns;
    scVulns.style.color = nVulns > 0 ? "var(--orange)" : "var(--green)";

    if (data.evpc_score !== null && data.evpc_score !== undefined) {
      scEvpc.textContent = data.evpc_score.toFixed(1);
      scEvpc.style.color = data.evpc_score === 1.0 ? "var(--green)"
                         : data.evpc_score >= 0.5  ? "var(--orange)"
                         : "var(--red)";
    } else {
      scEvpc.textContent = "N/A";
      scEvpc.style.color = "var(--dim)";
    }

    show(resultStats);

    // Diff viewer
    if (data.original_code && data.fixed_code) {
      renderDiff(data.original_code, data.fixed_code);
      show(diffContainer);
    }

    // Actions
    show(resultActions);

    runBtn.disabled = false;
    runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Again';
  }

  /* ── Diff viewer ── */
  function renderDiff(original, fixed) {
    const origLines  = original.split("\n");
    const fixedLines = fixed.split("\n");
    const diffLines  = computeDiff(origLines, fixedLines);

    // Diff tab
    diffBody.innerHTML = "";
    diffLines.forEach(line => {
      const el = document.createElement("div");
      el.className = "diff-line " + line.type;
      el.innerHTML = `<div class="diff-line-num">${line.num || ""}</div>
                      <div class="diff-line-content">${escapeHtml(line.text)}</div>`;
      diffBody.appendChild(el);
    });

    // Tab switching
    diffTabs.forEach(tab => {
      tab.addEventListener("click", () => {
        diffTabs.forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        const which = tab.dataset.tab;
        if (which === "diff") {
          diffBody.innerHTML = "";
          diffLines.forEach(line => {
            const el = document.createElement("div");
            el.className = "diff-line " + line.type;
            el.innerHTML = `<div class="diff-line-num">${line.num || ""}</div>
                            <div class="diff-line-content">${escapeHtml(line.text)}</div>`;
            diffBody.appendChild(el);
          });
        } else {
          const code = which === "original" ? original : fixed;
          diffBody.innerHTML = `<div class="plain-code">${escapeHtml(code)}</div>`;
        }
      });
    });
  }

  /* ── Simple diff algorithm (LCS-based) ── */
  function computeDiff(a, b) {
    const result = [];
    let ai = 0, bi = 0;
    const maxLen = Math.max(a.length, b.length);

    while (ai < a.length || bi < b.length) {
      const aLine = a[ai], bLine = b[bi];

      if (ai >= a.length) {
        result.push({ type: "add", text: "+ " + bLine, num: bi + 1 }); bi++;
      } else if (bi >= b.length) {
        result.push({ type: "del", text: "- " + aLine, num: ai + 1 }); ai++;
      } else if (aLine === bLine) {
        result.push({ type: "", text: "  " + aLine, num: ai + 1 }); ai++; bi++;
      } else {
        // Look ahead to find matching line
        let matched = false;
        for (let lookahead = 1; lookahead <= 5; lookahead++) {
          if (b[bi + lookahead] === aLine) {
            for (let k = 0; k < lookahead; k++) {
              result.push({ type: "add", text: "+ " + b[bi + k], num: bi + k + 1 });
              bi++;
            }
            matched = true; break;
          }
          if (a[ai + lookahead] === bLine) {
            for (let k = 0; k < lookahead; k++) {
              result.push({ type: "del", text: "- " + a[ai + k], num: ai + k + 1 });
              ai++;
            }
            matched = true; break;
          }
        }
        if (!matched) {
          result.push({ type: "del", text: "- " + aLine, num: ai + 1 }); ai++;
          result.push({ type: "add", text: "+ " + bLine, num: bi + 1 }); bi++;
        }
      }
    }
    return result;
  }

  /* ── Pipeline step indicator ── */
  function updatePipelineStep(event) {
    if (!event.agent) return;
    const agentName = event.agent.toLowerCase();
    const stepEl = document.getElementById("ps-" + agentName);
    if (!stepEl) return;

    if (event.type === "agent_start") {
      stepEl.classList.add("active");
      stepEl.classList.remove("done", "error");
    } else if (event.type === "agent_done") {
      stepEl.classList.remove("active");
      stepEl.classList.add("done");
    } else if (event.type === "error") {
      stepEl.classList.add("error");
      stepEl.classList.remove("active");
    }
  }

  /* ── Live log ── */
  function appendLog(event) {
    const el = document.createElement("div");
    el.className = "log-entry " + (event.type || "");

    const agent = event.agent ? `[${event.agent.toUpperCase()}] ` : "";
    const msg   = event.message || (event.data ? JSON.stringify(event.data) : "");

    el.textContent = `${agent}${msg}`;
    liveLogBody.appendChild(el);
    liveLogBody.scrollTop = liveLogBody.scrollHeight;
  }

  /* ── Downloads ── */
  btnDownload.addEventListener("click", () => {
    if (!auditResult?.fixed_code) return;
    const blob = new Blob([auditResult.fixed_code], { type: "text/plain" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = "fixed_" + (currentFile?.name || "code.py");
    a.click(); URL.revokeObjectURL(url);
  });

  btnReport.addEventListener("click", async () => {
    if (!jobId) return;
    btnReport.textContent = "Generating...";
    // PDF generation via Streamlit/FastAPI report endpoint (if implemented)
    // For now, open the result as JSON for the user
    const url = `${API_BASE}/api/result/${jobId}`;
    window.open(url, "_blank");
    btnReport.textContent = "Open Report Data";
  });

  btnReset.addEventListener("click", resetAll);

  /* ── Reset ── */
  function resetResults() {
    hide(resultStats);
    hide(diffContainer);
    hide(resultActions);
    liveLogBody.innerHTML = "";
    // Reset pipeline steps
    document.querySelectorAll(".pipeline-step").forEach(s => {
      s.classList.remove("active", "done", "error");
    });
  }

  function resetAll() {
    resetResults();
    hide(liveLog);
    show(emptyState);
    clearFile();
    jobId = null; auditResult = null;
    runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Audit';
  }

  /* ── Helpers ── */
  function show(el) { if (el) el.classList.remove("hidden"); }
  function hide(el) { if (el) el.classList.add("hidden"); }
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}
