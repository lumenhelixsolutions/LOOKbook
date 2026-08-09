/* lookBOOK Demo Lab — wired to lab_server.py (R2–R8) */

const LAB_API = localStorage.getItem('lb:labUrl') || 'http://localhost:8042';
const SETTINGS_KEY = 'lb:labSettings';
const WIZARD_KEY = 'lb:wizardDone';

let currentFile = null;
let imageMeta = {};
let panels = [];
let ocrBlocks = [];
let characters = [];
let projectId = null;
let labOnline = false;
let labServerVersion = 0;
let sceneSummary = null;
let pageInterpretation = null;
let interpretMethod = 'classical';
let labCapabilities = null;
let labMode = 'checking';
let projectHasSource = false;
let settings = { quality: 'balanced', vision: false, labUrl: LAB_API, cineforgeUrl: 'http://127.0.0.1:8765' };

const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const canvasWrap = document.getElementById('canvasWrap');
const canvas = document.getElementById('previewCanvas');
const ctx = canvas.getContext('2d');
const resultsArea = document.getElementById('resultsArea');
const runBtn = document.getElementById('runBtn');
const resetBtn = document.getElementById('resetBtn');
const statusBar = document.getElementById('statusBar');
const statusText = document.getElementById('statusText');
const directorPreview = document.getElementById('directorPreview');
const livingFrame = document.getElementById('livingFrame');
const vaultInput = document.getElementById('vaultManifest');
const livingStatus = document.getElementById('livingStatus');
const directorStatus = document.getElementById('directorStatus');
const btnBuildLiving = document.getElementById('btnBuildLiving');
const btnRefreshLiving = document.getElementById('btnRefreshLiving');

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) settings = { ...settings, ...JSON.parse(raw) };
  } catch { /* ignore */ }
}

function saveSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  localStorage.setItem('lb:labUrl', settings.labUrl || LAB_API);
}

function setStep(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'step';
  if (state) el.classList.add(state);
}

function setStatus(mode, text) {
  labMode = mode;
  statusBar.className = `status-bar ${mode}`;
  statusText.textContent = text;
}

async function checkLabHealth() {
  const base = apiBase();
  try {
    const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) throw new Error('health failed');
    const data = await res.json();
    labOnline = Boolean(data.ok);
    labServerVersion = Number(data.version) || 0;
    labCapabilities = data.capabilities || null;
    const ver = labServerVersion ? ` v${labServerVersion}` : '';
    const stale = labServerVersion && labServerVersion < 5 ? ' · restart server for Gen 2 pipeline' : '';
    const cap = labCapabilities;
    let capHint = '';
    if (cap && !cap.ready_for_pipeline) {
      capHint = ` · missing: ${(cap.notes || []).slice(0, 1).join('')}`;
      setStatus('simulated', `Lab online but not pipeline-ready${capHint}`);
      const badge = document.getElementById('modeBadge');
      if (badge) badge.textContent = 'Install lookbook-ai[lab] + Tesseract';
      return false;
    }
    setStatus('online', `Lab ready${ver}${stale} · panels+OCR+interpret · ${base}`);
    const badge = document.getElementById('modeBadge');
    if (badge) {
      badge.textContent = cap?.vision_llm ? 'Full pipeline · vision available' : 'Full pipeline · classical interpret';
    }
    return true;
  } catch {
    labOnline = false;
    setStatus('simulated', `Lab server offline — browser simulation (${base})`);
    const badge = document.getElementById('modeBadge');
    if (badge) badge.textContent = 'Simulated pipeline · start lab_server for real OCR';
    return false;
  }
}

function resetAll() {
  currentFile = null;
  imageMeta = {};
  panels = [];
  ocrBlocks = [];
  characters = [];
  projectId = null;
  projectHasSource = false;
  sceneSummary = null;
  pageInterpretation = null;
  interpretMethod = 'classical';
  canvasWrap.classList.remove('show');
  resultsArea.innerHTML = '';
  if (directorPreview) directorPreview.textContent = 'Run pipeline to preview director packet.';
  if (livingFrame) livingFrame.removeAttribute('src');
  ['s1', 's2', 's3', 's4', 's5', 's6', 's7'].forEach((id) => setStep(id, ''));
}

async function uploadToLab(path, file, reuseProjectId = null) {
  const fd = new FormData();
  fd.append('file', file);
  const qs = reuseProjectId ? `?project_id=${encodeURIComponent(reuseProjectId)}` : '';
  const res = await fetch(`${settings.labUrl || LAB_API}${path}${qs}`, { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed: ${path}`);
  return data;
}

function ocrBlocksForServer() {
  const srcW = imageMeta.width || canvas.width;
  const srcH = imageMeta.height || canvas.height;
  const scaleX = srcW / canvas.width;
  const scaleY = srcH / canvas.height;
  return ocrBlocks.map((b) => {
    const panelIdx = b.panel ?? 0;
    const panel = panels[panelIdx];
    const bbox = panel
      ? {
          x: Math.round(panel.x * scaleX),
          y: Math.round(panel.y * scaleY),
          w: Math.round(panel.w * scaleX),
          h: Math.round(panel.h * scaleY),
        }
      : {
          x: Math.round((b.x || 0) * scaleX),
          y: Math.round((b.y || 0) * scaleY),
          w: 120,
          h: 40,
        };
    return {
      text: b.text,
      classification: b.classification,
      conf: b.conf,
      bbox,
    };
  });
}

async function refreshProjectState() {
  if (!projectId || !labOnline) {
    projectHasSource = false;
    return null;
  }
  try {
    const res = await fetch(`${apiBase()}/api/project/${projectId}`);
    if (!res.ok) return null;
    const data = await res.json();
    projectHasSource = Boolean(data.has_source_image);
    return data;
  } catch {
    projectHasSource = false;
    return null;
  }
}

async function loadProjectSourcePreview(preferredRelPath = null) {
  if (!projectId || !labOnline) return false;
  const data = await refreshProjectState();
  if (!data?.has_source_image) return false;
  const rel = preferredRelPath || data.source_files?.[0] || 'source.png';
  const url = `${apiBase()}/api/project/${projectId}/file/${rel}`;
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      imageMeta = { width: img.width, height: img.height, name: rel.split('/').pop() };
      canvas.width = Math.min(img.width, 800);
      canvas.height = canvas.width * (img.height / img.width);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvasWrap.classList.add('show');
      currentFile = null;
      resolve(true);
    };
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

async function loadAnalysisFromServer() {
  if (!projectId || !labOnline) return;
  try {
    const data = await refreshProjectState();
    if (!data) return;
    const analysis = data.analysis || {};
    const scaleX = canvas.width / (imageMeta.width || canvas.width);
    const scaleY = canvas.height / (imageMeta.height || canvas.height);
    if (analysis.ocr_result?.blocks?.length) {
      ocrBlocks = mapOcrBlocks(analysis.ocr_result.blocks, panels, scaleX, scaleY);
    }
    if (analysis.character_analysis?.characters?.length) {
      characters = mapServerCharacters(analysis.character_analysis.characters);
    }
    if (analysis.scene_graph?.scenes?.length) {
      sceneSummary = analysis.scene_graph.scenes;
    }
    if (analysis.page_interpretation?.page_description) {
      pageInterpretation = analysis.page_interpretation.page_description;
    }
    drawOverlay();
  } catch { /* optional refresh */ }
}

function mapServerCharacters(chars) {
  return (chars || []).map((c) => ({
    name: c.name || c.character_id || 'Character',
    appearances: c.appearances ?? (c.panels || []).length,
    panels: (c.panels || []).map((p) => p.panel_index),
    description: c.description || '',
  }));
}

async function interpretPage(id, useVision = false) {
  const res = await fetch(`${apiBase()}/api/interpret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: id, use_vision: useVision }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(friendlyApiError(res.status, data));
  return data.interpretation || {};
}

function apiBase() {
  return (settings.labUrl || LAB_API).replace(/\/$/, '');
}

function friendlyApiError(status, body) {
  const msg = typeof body === 'string' ? body : body?.error;
  if (msg === 'Not found') {
    return 'Lab server is out of date — stop it and run: python -m lookbook.lab_server';
  }
  if (msg === 'Project not found') {
    return 'Project missing on server — run the pipeline again on your image.';
  }
  return msg || `Request failed (${status})`;
}

async function fetchWithTimeout(url, options = {}, ms = 60000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error('Request timed out — the server may be busy. Wait a moment and try Build & play again.');
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function setLivingUi(state, detail = '') {
  if (!livingStatus) return;
  const labels = {
    idle: 'Run the pipeline on an image to generate a playable storyboard review.',
    building: 'Building choreography and living-panels player…',
    ready: 'Click Play in the player below — panel art highlights and dialogue is read aloud.',
    error: detail || 'Could not build living panels.',
  };
  livingStatus.textContent = labels[state] || detail;
  if (btnBuildLiving) btnBuildLiving.disabled = state === 'building' || !projectId;
  if (btnRefreshLiving) btnRefreshLiving.disabled = !projectId || state === 'building';
}

async function buildLivingPanels() {
  if (!projectId || !labOnline) {
    showToast('Run the pipeline on an image first');
    return;
  }
  if (labServerVersion && labServerVersion < 5) {
    setLivingUi('error', 'Restart lab server: python -m lookbook.lab_server');
    showToast('Lab server needs a restart for Build & play');
    return;
  }
  setLivingUi('building');
  setStep('s5', 'active');
  try {
    const playUrl = `${apiBase()}/api/living-panels/${projectId}?build=${Date.now()}`;
    const res = await fetchWithTimeout(playUrl, {}, 90000);
    if (!res.ok) {
      let errBody = '';
      try { errBody = await res.json(); } catch { errBody = await res.text(); }
      throw new Error(friendlyApiError(res.status, errBody));
    }
    const html = await res.text();
    if (!html.toLowerCase().includes('living panels') && !html.includes('id="stage"')) {
      throw new Error('Server returned an unexpected page — restart the lab server.');
    }

    setStep('s5', 'done');
    setStep('s6', 'active');
    livingFrame.classList.remove('empty');
    livingFrame.src = playUrl;
    setStep('s6', 'done');

    let lineHint = '';
    try {
      const projRes = await fetch(`${apiBase()}/api/project/${projectId}`);
      if (projRes.ok) {
        const proj = await projRes.json();
        const lines = proj.analysis?.choreography?.total_lines;
        if (lines != null) lineHint = `${lines} line(s) · `;
      }
    } catch { /* optional */ }

    setLivingUi('ready', `${lineHint}click Play in the player — panel highlights + voice`);
    showToast('Living panels ready — click Play in the player below');
    livingFrame?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    setStep('s5', '');
    setLivingUi('error', e.message);
    showToast(e.message);
  }
}

function mapServerPanels(serverPanels, scaleX, scaleY) {
  return (serverPanels || []).map((p, i) => {
    const b = p.bbox || p;
    return {
      x: (b.x || 0) * scaleX,
      y: (b.y || 0) * scaleY,
      w: (b.w || 0) * scaleX,
      h: (b.h || 0) * scaleY,
      index: p.panel_index ?? i,
    };
  });
}

function mapOcrBlocks(blocks, panelsList, scaleX, scaleY) {
  return (blocks || []).map((b, i) => {
    const bbox = b.bbox || {};
    const panelIdx = panelsList.length ? i % panelsList.length : 0;
    const panel = panelsList[panelIdx] || { x: 10, y: 10, h: 40, w: 40 };
    const text = String(b.text || '').trim();
    let classification = b.classification || 'caption';
    if (!b.classification) {
      if (text.startsWith('"') || text.includes('?')) classification = 'dialogue';
      else if (text === text.toUpperCase() && text.length < 12) classification = 'sfx';
      else if (text.length > 60) classification = 'narration';
    }
    const bx = bbox.x ?? bbox.left ?? panel.x + 10;
    const by = bbox.y ?? bbox.top ?? panel.y + 10;
    const bw = bbox.w ?? bbox.width ?? Math.max(40, panel.w * 0.4);
    const bh = bbox.h ?? bbox.height ?? Math.max(24, panel.h * 0.15);
    return {
      text,
      classification,
      panel: panelIdx,
      conf: Math.round(b.conf || b.confidence || 75),
      x: bx * scaleX,
      y: by * scaleY,
      w: bw * scaleX,
      h: bh * scaleY,
    };
  });
}

function drawOverlay() {
  const img = new Image();
  img.src = canvas.toDataURL();
  img.onload = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const colors = ['#ffb042', '#f2ba46', '#f472b6', '#a78bfa', '#34d399', '#f97316', '#60a5fa'];
    panels.forEach((p, i) => {
      ctx.strokeStyle = colors[i % colors.length];
      ctx.lineWidth = 3;
      ctx.setLineDash([6, 4]);
      ctx.strokeRect(p.x, p.y, p.w, p.h);
      ctx.setLineDash([]);
      ctx.fillStyle = colors[i % colors.length];
      ctx.font = 'bold 14px Inter, sans-serif';
      ctx.fillText(`Panel ${p.index + 1}`, p.x + 8, p.y + 22);
    });
    const bubbleColors = {
      dialogue: '#f2ba46',
      narration: '#a78bfa',
      sfx: '#f472b6',
      caption: '#60a5fa',
    };
    ocrBlocks.forEach((b) => {
      const col = bubbleColors[b.classification] || '#60a5fa';
      const bw = b.w || 80;
      const bh = b.h || 28;
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.strokeRect(b.x, b.y, bw, bh);
      ctx.fillStyle = col + '33';
      ctx.fillRect(b.x, b.y, bw, bh);
      ctx.fillStyle = col;
      ctx.font = '11px Inter, sans-serif';
      const label = b.text.length > 28 ? `${b.text.slice(0, 28)}…` : b.text;
      ctx.fillText(label, b.x + 4, b.y + 14);
    });
  };
}

/* --- Simulated fallback (R1 honest labeling) --- */
function detectPanelsSim(ctxLocal, w, h) {
  const results = [];
  const minW = w * 0.08;
  const minH = h * 0.08;
  const imageData = ctxLocal.getImageData(0, 0, w, h);
  const data = imageData.data;
  const gray = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const idx = i * 4;
    gray[i] = (data[idx] * 0.299 + data[idx + 1] * 0.587 + data[idx + 2] * 0.114) | 0;
  }
  const hProjection = new Uint32Array(h);
  const vProjection = new Uint32Array(w);
  const threshold = 180;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (gray[y * w + x] > threshold) hProjection[y]++;
    }
  }
  for (let x = 0; x < w; x++) {
    for (let y = 0; y < h; y++) {
      if (gray[y * w + x] > threshold) vProjection[x]++;
    }
  }
  const hGutters = [];
  const vGutters = [];
  const gutterRatio = 0.15;
  for (let y = 0; y < h; y++) {
    if (hProjection[y] < w * gutterRatio) hGutters.push(y);
  }
  for (let x = 0; x < w; x++) {
    if (vProjection[x] < h * gutterRatio) vGutters.push(x);
  }
  const rows = segmentIndices(hGutters, h);
  const cols = segmentIndices(vGutters, w);
  for (const row of rows) {
    for (const col of cols) {
      const pw = col[1] - col[0];
      const ph = row[1] - row[0];
      if (pw < minW || ph < minH) continue;
      if (pw < w * 0.03 || ph < h * 0.03) continue;
      results.push({
        x: col[0], y: row[0], w: pw, h: ph,
        cx: col[0] + pw / 2, cy: row[0] + ph / 2,
        index: results.length,
      });
    }
  }
  if (results.length === 0) {
    results.push({ x: 5, y: 5, w: w - 10, h: h - 10, cx: w / 2, cy: h / 2, index: 0 });
  }
  return results;
}

function segmentIndices(gutters, totalLen) {
  if (gutters.length === 0) return [[0, totalLen]];
  const segs = [];
  let start = 0;
  let inGutter = false;
  for (let i = 0; i < totalLen; i++) {
    const isGutter = gutters.includes(i);
    if (isGutter && !inGutter) {
      if (i - start > totalLen * 0.03) segs.push([start, i]);
      inGutter = true;
    } else if (!isGutter && inGutter) {
      start = i;
      inGutter = false;
    }
  }
  if (!inGutter && totalLen - start > totalLen * 0.03) segs.push([start, totalLen]);
  return segs.length ? segs : [[0, totalLen]];
}

function simulateOCR(panelsList) {
  const classifications = ['dialogue', 'narration', 'sfx', 'caption'];
  const dialogueTexts = ['"What happened here?"', '"We need answers."', '"Look over there!"'];
  const narrationTexts = ['Meanwhile, across the city…', 'The truth was closer than they thought.'];
  const sfxTexts = ['BOOM', 'CRASH', 'WHAM'];
  return panelsList.map((p, i) => {
    const type = classifications[i % classifications.length];
    let text;
    if (type === 'dialogue') text = dialogueTexts[i % dialogueTexts.length];
    else if (type === 'narration') text = narrationTexts[i % narrationTexts.length];
    else if (type === 'sfx') text = sfxTexts[i % sfxTexts.length];
    else text = 'Ambient scene description.';
    return { text, classification: type, panel: i, conf: 72 + (i * 3) % 20, x: p.x + 10, y: p.y + p.h / 2 };
  });
}

function simulateCharacters(panelsList) {
  const names = ['Hero', 'Sidekick', 'Villain'];
  return names.map((name, i) => ({
    name,
    appearances: Math.max(1, panelsList.length - i),
    panels: panelsList.map((_, idx) => idx).filter((idx) => idx % (i + 2) === 0),
  })).filter((c) => c.panels.length > 0);
}

async function invokeDirectorGraphIfAvailable() {
  if (!projectId || !labOnline || !labCapabilities?.director_graph) return null;
  try {
    const res = await fetch(`${apiBase()}/api/director-graph/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, profile_id: 'classical-runway' }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Director graph run failed');
      return null;
    }
    if (!data.ok) {
      showToast(data.error || 'Director graph returned errors');
      return null;
    }
    return data;
  } catch (e) {
    showToast(String(e.message || e));
    return null;
  }
}

async function loadDirectorPreview() {
  if (!projectId || !labOnline || !directorPreview) return;
  try {
    const res = await fetch(`${apiBase()}/api/director-preview/${projectId}?target=runway`);
    const data = await res.json();
    if (res.ok) {
      directorPreview.textContent = data.markdown || '(empty director packet)';
      if (directorStatus) {
        if (data.source === 'director-graph') {
          const shots = data.shot_count != null ? `${data.shot_count} shots · ` : '';
          directorStatus.textContent = `${shots}Director graph sidecar — full shot packet`;
        } else if (data.markdown?.includes('Shot Director Notes')) {
          directorStatus.textContent = 'Director AI packet — shot-level notes ready.';
        } else if (data.source === 'lab-stub') {
          directorStatus.textContent = 'Lab preview — run director-graph sidecar for full shot notes.';
        } else {
          directorStatus.textContent = 'Director packet ready.';
        }
      }
    } else {
      directorPreview.textContent = data.error || 'Director packet unavailable';
    }
  } catch (e) {
    directorPreview.textContent = String(e.message || e);
  }
}

function loadLivingPanels(force = false) {
  if (!projectId || !labOnline || !livingFrame) return;
  const base = settings.labUrl || LAB_API;
  livingFrame.classList.remove('empty');
  livingFrame.src = `${base}/api/living-panels/${projectId}${force ? `?t=${Date.now()}` : ''}`;
}

async function runUnifiedPipeline() {
  const w = canvas.width;
  const h = canvas.height;
  const scaleX = w / (imageMeta.width || w);
  const scaleY = h / (imageMeta.height || h);
  const qs = new URLSearchParams({
    use_vision: settings.vision ? 'true' : 'false',
  });
  if (projectId) qs.set('project_id', projectId);
  let res;
  if (currentFile) {
    const fd = new FormData();
    fd.append('file', currentFile);
    res = await fetch(`${apiBase()}/api/pipeline/run?${qs}`, { method: 'POST', body: fd });
  } else if (projectId && projectHasSource) {
    res = await fetch(`${apiBase()}/api/pipeline/run?${qs}`, {
      method: 'POST',
      headers: { 'Content-Length': '0' },
    });
  } else {
    throw new Error('No source image — drop a page or import vault with an image');
  }
  const data = await res.json();
  if (!res.ok) throw new Error(friendlyApiError(res.status, data));
  projectId = data.project_id;
  const pipe = data.pipeline || {};
  setStep('s1', 'done');
  setStep('s2', 'active');
  panels = mapServerPanels(pipe.panels, scaleX, scaleY);
  setStep('s2', 'done');
  setStep('s3', 'active');
  ocrBlocks = mapOcrBlocks(pipe.ocr_blocks, panels, scaleX, scaleY);
  if (pipe.ocr_fallback || pipe.ocr_synthesized) {
    showToast(pipe.ocr_error || 'OCR used fallback — check Tesseract');
  }
  setStep('s3', 'done');
  setStep('s4', 'active');
  const interpretation = pipe.interpretation || {};
  characters = mapServerCharacters(interpretation.characters);
  sceneSummary = interpretation.scenes || [];
  pageInterpretation = interpretation.page_description || null;
  interpretMethod = interpretation.method || 'classical';
  surfaceVisionInterpretStatus(interpretation);
  await loadAnalysisFromServer();
  setStep('s4', 'done');
  drawOverlay();
}

async function runPipeline() {
  if (!currentFile && !(projectId && projectHasSource)) {
    showToast('Drop a comic page or import vault with a source image');
    return;
  }
  if (!currentFile && projectId && projectHasSource && !canvasWrap.classList.contains('show')) {
    await loadProjectSourcePreview();
  }
  runBtn.disabled = true;
  const w = canvas.width;
  const h = canvas.height;
  const scaleX = w / (imageMeta.width || w);
  const scaleY = h / (imageMeta.height || h);

  setStep('s1', 'active');
  try {
    if (labOnline) {
      if (labServerVersion >= 5) {
        await runUnifiedPipeline();
      } else {
        const analyzeData = await uploadToLab('/api/analyze', currentFile);
        projectId = analyzeData.project_id;
        setStep('s1', 'done');
        setStep('s2', 'active');
        const panelData = await uploadToLab('/api/panels', currentFile, projectId);
        projectId = panelData.project_id || projectId;
        panels = mapServerPanels(panelData.panels, scaleX, scaleY);
        setStep('s2', 'done');
        setStep('s3', 'active');
        const ocrData = await uploadToLab('/api/extract-text', currentFile, projectId);
        ocrBlocks = mapOcrBlocks(ocrData.blocks, panels, scaleX, scaleY);
        setStep('s3', 'done');
        setStep('s4', 'active');
        const interpretation = await interpretPage(projectId, settings.vision);
        characters = mapServerCharacters(interpretation.characters);
        sceneSummary = interpretation.scenes || [];
        pageInterpretation = interpretation.page_description || null;
        interpretMethod = interpretation.method || 'classical';
        surfaceVisionInterpretStatus(interpretation);
        await loadAnalysisFromServer();
        setStep('s4', 'done');
        drawOverlay();
      }

      if (btnBuildLiving) btnBuildLiving.disabled = false;
      if (btnRefreshLiving) btnRefreshLiving.disabled = false;

      await buildLivingPanels();
      await invokeDirectorGraphIfAvailable();
      await loadDirectorPreview();
      if (labServerVersion < 5) {
        surfaceVisionInterpretStatus({ method: interpretMethod });
      }
      setStep('s7', 'done');
      showResults(true);
    } else {
      setStep('s1', 'done');
      setStep('s2', 'active');
      panels = detectPanelsSim(ctx, w, h);
      drawOverlay();
      setStep('s2', 'done');
      setStep('s3', 'active');
      ocrBlocks = simulateOCR(panels);
      setStep('s3', 'done');
      setStep('s4', 'active');
      characters = simulateCharacters(panels);
      setStep('s4', 'done');
      setStep('s5', 'done');
      setStep('s6', 'done');
      setStep('s7', 'done');
      showResults(false);
    }
  } catch (e) {
    resultsArea.innerHTML = `<div style="color:#f87171;font-size:14px">Pipeline error: ${e.message}</div>`;
    setStatus('offline', `Pipeline failed — ${e.message}`);
  } finally {
    runBtn.disabled = false;
  }
}

function showResults(realPipeline) {
  let html = `
    <div class="results-grid">
      <div class="stat"><div class="num">${panels.length}</div><div class="lbl">Panels Detected</div></div>
      <div class="stat"><div class="num">${ocrBlocks.length}</div><div class="lbl">Text Blocks</div></div>
      <div class="stat"><div class="num">${characters.length}</div><div class="lbl">Characters Tracked</div></div>
      <div class="stat"><div class="num">${(imageMeta.width || 0)}×${(imageMeta.height || 0)}</div><div class="lbl">Source Resolution</div></div>
    </div>
    <p style="font-size:12px;color:var(--muted);margin-top:10px">${realPipeline ? `Real Python pipeline · ${interpretMethod}` : 'Simulated browser pipeline'}${projectId ? ` · project <code>${projectId}</code>` : ''}</p>
  `;

  if (pageInterpretation) {
    html += `<h2 style="font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px">Page interpretation</h2>`;
    html += `<p style="font-size:13px;line-height:1.55;color:var(--ink);opacity:.9">${pageInterpretation}</p>`;
  }

  if (sceneSummary && sceneSummary.length) {
    html += `<h2 style="font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px">Scene breakdown</h2><ul class="ocr-list">`;
    sceneSummary.forEach((s) => {
      const dlg = (s.dialogue || []).join(' · ') || '(no dialogue)';
      const nar = (s.narration || []).length ? ` — ${s.narration.join(' · ')}` : '';
      html += `<li class="narration">Scene ${s.scene_index ?? 0} (${s.panel_count ?? 0} panels): ${dlg}${nar}</li>`;
    });
    html += '</ul>';
  }

  if (ocrBlocks.length) {
    html += `<h2 style="font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px">Text Classification</h2><ul class="ocr-list">`;
    ocrBlocks.forEach((b) => {
      const icon = b.classification === 'dialogue' ? '💬' : b.classification === 'sfx' ? '💥' : b.classification === 'narration' ? '📖' : '📝';
      html += `<li class="${b.classification}">${icon} <strong>${b.classification}</strong> (${b.conf}%): ${b.text}</li>`;
    });
    html += '</ul>';
  }

  if (characters.length) {
    html += `<h2 style="font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px">Character Tracking</h2>`;
    characters.forEach((c) => {
      const desc = c.description ? `<br><span style="color:var(--muted);font-size:12px">${c.description}</span>` : '';
      html += `<div style="padding:6px 0;font-size:13px"><strong>${c.name}</strong> — ${c.appearances} panel(s): [${c.panels.join(', ')}]${desc}</div>`;
    });
  }

  html += `<h2 style="font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px">Exports</h2><div class="export-grid">`;
  const chips = [
    { label: 'Living Panels', action: 'living' },
    { label: 'Director Packet', action: 'director' },
    { label: 'Project JSON', action: 'project' },
    { label: 'CineForge', action: 'cineforge' },
  ];
  chips.forEach((c) => {
    html += `<span class="chip" data-export="${c.action}">${c.label}</span>`;
  });
  html += '</div>';

  resultsArea.innerHTML = html;
  resultsArea.querySelectorAll('[data-export]').forEach((chip) => {
    chip.addEventListener('click', () => handleExport(chip.dataset.export));
  });
}

function handleExport(kind) {
  if (!projectId && labOnline) {
    alert('Run the pipeline first to create a project.');
    return;
  }
  const base = settings.labUrl || LAB_API;
  if (kind === 'living') {
    buildLivingPanels().then(() => livingFrame?.scrollIntoView({ behavior: 'smooth' }));
  } else if (kind === 'director') {
    loadDirectorPreview();
    directorPreview?.scrollIntoView({ behavior: 'smooth' });
  } else if (kind === 'project' && projectId) {
    window.open(`${base}/api/project/${projectId}`, '_blank');
  } else if (kind === 'cineforge') {
    exportToCineforge();
  }
}

async function exportToCineforge() {
  if (!projectId) {
    alert('Run the pipeline first to create a project.');
    return;
  }
  if (!labOnline) {
    alert('Start lab_server.py to export to CineForge.');
    return;
  }
  const cineforgeUrl = (settings.cineforgeUrl || 'http://127.0.0.1:8765').replace(/\/$/, '');
  let cineforgeProjectId = (settings.cineforgeProjectId || '').trim();
  const push = window.confirm(
    'Push shot graph to a running CineForge backend?\n\nOK = push (needs project ID)\nCancel = export file only',
  );
  if (push && !cineforgeProjectId) {
    cineforgeProjectId = (prompt('CineForge project ID (create at ' + cineforgeUrl + '/projects)') || '').trim();
    if (!cineforgeProjectId) return;
    settings.cineforgeProjectId = cineforgeProjectId;
    saveSettings();
  }
  try {
    const res = await fetch(`${apiBase()}/api/export-cineforge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        push,
        cineforge_url: cineforgeUrl,
        cineforge_project_id: push ? cineforgeProjectId : undefined,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Export failed');
    if (data.pushed && data.cineforge_ui_url) {
      showToast(`CineForge ingest · ${data.shot_count} shot(s) · ${data.choreography_lines || 0} choreography line(s)`);
      window.open(data.cineforge_ui_url, '_blank');
    } else {
      showToast(`CineForge export ready · ${data.shot_count} shot(s) → ${data.output_path || 'exports/cineforge/ingest.json'}`);
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function handleFile(f) {
  resetAll();
  currentFile = f;
  const ext = f.name.split('.').pop().toLowerCase();
  if (['cbz', 'cbr', 'zip', 'rar'].includes(ext)) {
    resultsArea.innerHTML = `<div style="color:var(--muted);font-size:14px">Archive loaded: <strong>${f.name}</strong>. Use CLI for batch processing. Single-page preview only.</div>`;
    setStep('s1', 'done');
    return;
  }
  const url = URL.createObjectURL(f);
  const img = new Image();
  img.onload = () => {
    imageMeta = { width: img.width, height: img.height, name: f.name };
    canvas.width = Math.min(img.width, 800);
    canvas.height = canvas.width * (img.height / img.width);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    canvasWrap.classList.add('show');
    setStep('s1', 'done');
    runPipeline();
  };
  img.src = url;
}

async function importVaultManifest(file) {
  if (!file) return;
  const text = await file.text();
  let manifest;
  try {
    manifest = JSON.parse(text);
  } catch {
    alert('Invalid JSON manifest');
    return;
  }
  if (!labOnline) {
    alert('Start lab_server.py to import vault manifests.');
    return;
  }
  try {
    const res = await fetch(`${settings.labUrl || LAB_API}/api/import-vault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifest, project_id: projectId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Import failed');
    projectId = data.project_id;
    await refreshProjectState();
    const loaded = await loadProjectSourcePreview();
    showToast(
      loaded
        ? `Vault imported · ${data.import?.files_written || 0} file(s) — Run Pipeline uses project source`
        : `Vault imported · ${data.import?.files_written || 0} file(s) — add an image file to run pipeline`,
    );
    if (btnBuildLiving) btnBuildLiving.disabled = !projectHasSource;
  } catch (e) {
    alert(e.message);
  }
}

function showToast(msg, tone = 'info') {
  const el = document.createElement('div');
  el.textContent = msg;
  const border = tone === 'error' ? 'var(--danger, #f87171)' : 'var(--accent)';
  el.style.cssText = `position:fixed;bottom:20px;right:20px;background:var(--card);border:1px solid ${border};padding:10px 16px;border-radius:10px;font-size:13px;z-index:300;max-width:min(420px,90vw)`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), tone === 'error' ? 5200 : 2800);
}

function surfaceVisionInterpretStatus(interpretation = {}) {
  const method = interpretation.method || 'classical';
  if (interpretation.vision_error) {
    showToast(`Vision LLM failed: ${interpretation.vision_error}`, 'error');
    if (directorStatus) {
      directorStatus.textContent = `Vision error — showing classical results. ${interpretation.vision_error}`;
    }
    return;
  }
  if (interpretation.vision_skipped) {
    if (settings.vision) {
      showToast(interpretation.vision_skipped);
    }
    if (directorStatus) {
      directorStatus.textContent = interpretation.vision_skipped;
    }
    return;
  }
  if (method === 'vision') {
    if (directorStatus) {
      directorStatus.textContent = 'Vision interpretation — semantic page read from LLM.';
    }
    return;
  }
  if (directorStatus) {
    directorStatus.textContent = 'Classical interpretation — enable vision in Settings for semantic page read.';
  }
}

/* Wizard R3 */
async function runWizard() {
  const name = document.getElementById('wizardName')?.value?.trim() || 'My Story';
  const preset = document.getElementById('wizardPreset')?.value || 'comic';
  if (labOnline) {
    try {
      const res = await fetch(`${settings.labUrl || LAB_API}/api/new-project`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, preset }),
      });
      const data = await res.json();
      if (res.ok) {
        projectId = data.project_id;
        showToast(`Project "${name}" created (${preset})`);
      }
    } catch { /* optional */ }
  }
  localStorage.setItem(WIZARD_KEY, '1');
  document.getElementById('wizardOverlay')?.classList.remove('open');
}

function openWizardIfNeeded() {
  if (!localStorage.getItem(WIZARD_KEY)) {
    document.getElementById('wizardOverlay')?.classList.add('open');
  }
}

function bindUi() {
  drop.onclick = () => fileInput.click();
  ['dragenter', 'dragover'].forEach((e) =>
    drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add('drag'); })
  );
  ['dragleave', 'drop'].forEach((e) =>
    drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove('drag'); })
  );
  drop.addEventListener('drop', (ev) => {
    const f = ev.dataTransfer.files[0];
    if (f) handleFile(f);
  });
  fileInput.onchange = (e) => {
    if (e.target.files[0]) handleFile(e.target.files[0]);
  };
  resetBtn.onclick = resetAll;
  runBtn.onclick = () => runPipeline();

  document.getElementById('btnNewProject')?.addEventListener('click', () => {
    document.getElementById('wizardOverlay')?.classList.add('open');
  });
  document.getElementById('btnWizardSkip')?.addEventListener('click', () => {
    localStorage.setItem(WIZARD_KEY, '1');
    document.getElementById('wizardOverlay')?.classList.remove('open');
  });
  document.getElementById('btnWizardStart')?.addEventListener('click', runWizard);

  document.getElementById('btnSettings')?.addEventListener('click', () => {
    document.getElementById('settingQuality').value = settings.quality;
    document.getElementById('settingVision').checked = settings.vision;
    document.getElementById('settingLabUrl').value = settings.labUrl || LAB_API;
    const cfUrl = document.getElementById('settingCineforgeUrl');
    if (cfUrl) cfUrl.value = settings.cineforgeUrl || 'http://127.0.0.1:8765';
    const visionHint = document.getElementById('visionKeyHint');
    if (visionHint) {
      const provider = labCapabilities?.vision_provider || 'openai';
      const hasKey = Boolean(labCapabilities?.vision_llm);
      visionHint.textContent = hasKey
        ? `API key detected for ${provider}.`
        : `No API key for ${provider} — set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.`;
    }
    document.getElementById('settingsDrawer')?.classList.add('open');
  });
  document.getElementById('btnCloseSettings')?.addEventListener('click', () => {
    document.getElementById('settingsDrawer')?.classList.remove('open');
  });
  document.getElementById('btnSaveSettings')?.addEventListener('click', async () => {
    settings.quality = document.getElementById('settingQuality').value;
    settings.vision = document.getElementById('settingVision').checked;
    settings.labUrl = document.getElementById('settingLabUrl').value.trim() || LAB_API;
    const cfUrl = document.getElementById('settingCineforgeUrl');
    if (cfUrl) settings.cineforgeUrl = cfUrl.value.trim() || 'http://127.0.0.1:8765';
    saveSettings();
    document.getElementById('settingsDrawer')?.classList.remove('open');
    await checkLabHealth();
    if (settings.vision && labCapabilities && !labCapabilities.vision_llm) {
      const provider = labCapabilities.vision_provider || 'openai';
      showToast(`Vision enabled but no API key for ${provider}`);
    }
  });

  document.getElementById('btnVaultImport')?.addEventListener('click', () => vaultInput?.click());
  vaultInput?.addEventListener('change', (e) => {
    if (e.target.files[0]) importVaultManifest(e.target.files[0]);
  });

  btnBuildLiving?.addEventListener('click', buildLivingPanels);
  btnRefreshLiving?.addEventListener('click', () => loadLivingPanels(true));
}

async function boot() {
  loadSettings();
  bindUi();
  setStatus('checking', 'Checking lab server…');
  await checkLabHealth();
  openWizardIfNeeded();
}

boot();