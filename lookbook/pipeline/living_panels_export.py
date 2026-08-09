from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def export_living_panels(
    project: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Export a self-contained living-panels HTML review from choreography + panels."""
    project = Path(project)
    analysis = project / "analysis"

    choreo_path = analysis / "choreography.json"
    panel_path = analysis / "panel_analysis.json"
    shot_path = analysis / "shot_graph.json"

    if not choreo_path.exists():
        raise FileNotFoundError(
            f"Choreography not found at {choreo_path}. Run 'lookbook build-choreography' first."
        )
    if not panel_path.exists():
        raise FileNotFoundError(
            f"Panel analysis not found at {panel_path}. Run 'lookbook detect-panels' first."
        )

    choreography = json.loads(choreo_path.read_text(encoding="utf-8"))
    panels_data = json.loads(panel_path.read_text(encoding="utf-8"))
    shots: list[dict[str, Any]] = []
    if shot_path.exists():
        shots = json.loads(shot_path.read_text(encoding="utf-8")).get("shots", [])

    page_summary = ""
    interp_path = analysis / "page_interpretation.json"
    if interp_path.exists():
        try:
            page_summary = json.loads(interp_path.read_text(encoding="utf-8")).get("page_description") or ""
        except Exception:
            page_summary = ""

    if output is None:
        output = project / "exports" / "living_panels" / "review.html"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        rel_depth = len(output.parent.relative_to(project.resolve()).parts)
        rel_base = Path(*([".."] * rel_depth))
    except ValueError:
        rel_base = Path(".")

    panel_assets: list[dict[str, Any]] = []
    for p in panels_data.get("panels", []):
        img = p.get("image_path")
        rel_img = None
        if img:
            candidate = project / img
            if candidate.exists():
                rel_img = str((rel_base / img).as_posix())
        panel_assets.append(
            {
                "panel_index": p.get("panel_index"),
                "bbox": p.get("bbox", {}),
                "image": rel_img,
            }
        )

    payload = {
        "choreography": choreography,
        "panels": panel_assets,
        "shots": shots,
        "page_summary": page_summary,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    title = html.escape(project.name)

    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} · Living Panels</title>
  <style>
    :root {{
      --bg: #070a10;
      --ink: #fdf6d8;
      --accent: #1ae0cf;
      --gold: #e8c36a;
      --panel-border: rgba(255,255,255,.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(ellipse at 20% 0%, #121824 0%, var(--bg) 55%);
      color: var(--ink);
      font-family: system-ui, sans-serif;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 20px;
      border-bottom: 1px solid var(--panel-border);
    }}
    .badge {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: .18em;
      font-size: 11px;
      font-weight: 800;
    }}
    h1 {{ margin: 4px 0 0; font-size: 1.25rem; font-weight: 600; }}
    main {{ display: grid; grid-template-columns: 1fr 320px; gap: 16px; padding: 16px 20px 28px; }}
    @media (max-width: 900px) {{ main {{ grid-template-columns: 1fr; }} }}
    #stage-wrap {{
      position: relative;
      overflow: hidden;
      border-radius: 18px;
      border: 1px solid var(--panel-border);
      background: #0c1018;
      min-height: 420px;
    }}
    #stage {{
      display: flex;
      gap: 10px;
      padding: 14px;
      transition: transform .6s cubic-bezier(.2,.8,.2,1);
      will-change: transform;
    }}
    .panel-card {{
      flex: 0 0 auto;
      width: min(240px, 42vw);
      border-radius: 12px;
      border: 2px solid transparent;
      overflow: hidden;
      opacity: .45;
      transform: scale(.94);
      transition: opacity .35s, transform .35s, border-color .35s, box-shadow .35s;
    }}
    .panel-card.active {{
      opacity: 1;
      transform: scale(1);
      border-color: var(--gold);
      box-shadow: 0 0 28px rgba(232,195,106,.25);
    }}
    .panel-card img {{
      display: block;
      width: 100%;
      height: auto;
      background: #111;
    }}
    .panel-placeholder {{
      aspect-ratio: 3/4;
      display: grid;
      place-items: center;
      background: linear-gradient(145deg,#151b28,#0a0e16);
      color: rgba(255,255,255,.35);
      font-size: 12px;
    }}
    #bubble {{
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--panel-border);
      background: rgba(255,255,255,.04);
      min-height: 72px;
      line-height: 1.5;
    }}
    #speaker {{ font-size: 11px; text-transform: uppercase; letter-spacing: .14em; color: var(--gold); margin-bottom: 6px; }}
    #line-text .word {{ opacity: .55; transition: opacity .12s, color .12s; }}
    #line-text .word.spoken {{ opacity: 1; color: var(--accent); }}
    aside {{
      border-radius: 18px;
      border: 1px solid var(--panel-border);
      background: rgba(255,255,255,.03);
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    button {{
      border: 1px solid var(--panel-border);
      background: rgba(0,0,0,.25);
      color: var(--ink);
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 12px;
      cursor: pointer;
    }}
    button:hover {{ border-color: var(--accent); }}
    button:disabled {{ opacity: .4; cursor: default; }}
    #timeline {{ display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow: auto; }}
    .tl-item {{
      font-size: 12px;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid transparent;
      cursor: pointer;
      opacity: .7;
    }}
    .tl-item:hover, .tl-item.active {{ opacity: 1; border-color: var(--panel-border); background: rgba(255,255,255,.04); }}
    .tl-item .meta {{ font-size: 10px; opacity: .5; margin-top: 2px; }}
    #camera-tag {{ font-size: 11px; opacity: .55; font-family: ui-monospace, monospace; }}
  </style>
</head>
<body>
  <header>
    <div>
      <div class="badge">lookBOOK · living panels</div>
      <h1>{title}</h1>
      <p id="page-summary" style="margin:6px 0 0;font-size:13px;opacity:.72;max-width:52rem;line-height:1.45"></p>
    </div>
    <div id="camera-tag">camera: static</div>
  </header>
  <main>
    <section>
      <div id="stage-wrap"><div id="stage"></div></div>
      <div id="bubble">
        <div id="speaker">—</div>
        <div id="line-text">Press Play to hear the page.</div>
      </div>
    </section>
    <aside>
      <div class="controls">
        <button id="btn-play" type="button">Play</button>
        <button id="btn-pause" type="button" disabled>Pause</button>
        <button id="btn-prev" type="button">Prev</button>
        <button id="btn-next" type="button">Next</button>
      </div>
      <div id="play-status" style="font-size:11px;opacity:.65">Ready — press Play to hear dialogue</div>
      <div id="timeline"></div>
    </aside>
  </main>
  <script id="lookbook-data" type="application/json">{payload_json}</script>
  <script>
  (() => {{
    const data = JSON.parse(document.getElementById('lookbook-data').textContent);
    const lines = data.choreography.lines || [];
    const voiceCast = data.choreography.voice_cast || {{}};
    const panels = data.panels || [];
    const shots = data.shots || [];
    const pageSummary = data.page_summary || '';
    const stage = document.getElementById('stage');
    const pageSummaryEl = document.getElementById('page-summary');
    if (pageSummaryEl && pageSummary) pageSummaryEl.textContent = pageSummary;
    const timeline = document.getElementById('timeline');
    const speakerEl = document.getElementById('speaker');
    const lineTextEl = document.getElementById('line-text');
    const cameraTag = document.getElementById('camera-tag');
    const btnPlay = document.getElementById('btn-play');
    const btnPause = document.getElementById('btn-pause');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const playStatus = document.getElementById('play-status');

    let lineIndex = 0;
    let utterance = null;
    let spokenWord = -1;

    const panelEls = new Map();
    panels.forEach((p) => {{
      const card = document.createElement('div');
      card.className = 'panel-card';
      card.dataset.panelIndex = String(p.panel_index);
      if (p.image) {{
        const img = document.createElement('img');
        img.src = p.image;
        img.alt = 'Panel ' + p.panel_index;
        card.appendChild(img);
      }} else {{
        const ph = document.createElement('div');
        ph.className = 'panel-placeholder';
        ph.textContent = 'Panel ' + p.panel_index;
        card.appendChild(ph);
      }}
      stage.appendChild(card);
      panelEls.set(p.panel_index, card);
    }});

    function cameraForLine(line) {{
      const shot = shots.find((s) => (s.panels || []).includes(line.panel_index));
      return shot?.camera || 'static';
    }}

    function renderWords(line, highlight = -1) {{
      const words = line.words || [];
      lineTextEl.innerHTML = words.map((w, i) =>
        `<span class="word${{i <= highlight ? ' spoken' : ''}}">${{w}}</span>`
      ).join(' ') || line.text;
    }}

    function focusPanel(panelIndex, camera) {{
      panelEls.forEach((el, idx) => el.classList.toggle('active', idx === panelIndex));
      cameraTag.textContent = 'camera: ' + (camera || 'static');
      const card = panelEls.get(panelIndex);
      if (!card) return;
      const wrap = document.getElementById('stage-wrap');
      const cx = card.offsetLeft + card.offsetWidth / 2;
      const tx = wrap.clientWidth / 2 - cx;
      const scale = camera?.includes('push') || camera?.includes('zoom') ? 1.08 : 1.02;
      stage.style.transform = `translateX(${{tx}}px) scale(${{scale}})`;
    }}

    function setLine(idx) {{
      lineIndex = Math.max(0, Math.min(lines.length - 1, idx));
      const line = lines[lineIndex];
      if (!line) return;
      speakerEl.textContent = line.speaker;
      renderWords(line, spokenWord);
      focusPanel(line.panel_index, cameraForLine(line));
      timeline.querySelectorAll('.tl-item').forEach((el, i) => el.classList.toggle('active', i === lineIndex));
    }}

    lines.forEach((line, i) => {{
      const item = document.createElement('div');
      item.className = 'tl-item';
      item.innerHTML = `<div>${{line.text.slice(0, 72)}}${{line.text.length > 72 ? '…' : ''}}</div><div class="meta">${{line.speaker}} · panel ${{line.panel_index}}</div>`;
      item.addEventListener('click', () => {{ stopSpeech(); spokenWord = -1; setLine(i); }});
      timeline.appendChild(item);
    }});

    function pickVoice(speaker) {{
      const voices = speechSynthesis.getVoices();
      const hint = voiceCast[speaker] || {{}};
      const prefer = (hint.display_name || speaker || '').toLowerCase();
      return voices.find((v) => v.name.toLowerCase().includes('english')) || voices[0] || null;
    }}

    function speakCurrent() {{
      const line = lines[lineIndex];
      if (!line || !('speechSynthesis' in window)) return;
      stopSpeech();
      utterance = new SpeechSynthesisUtterance(line.text);
      const cast = voiceCast[line.speaker] || {{}};
      utterance.pitch = cast.pitch ?? 1;
      utterance.rate = cast.rate ?? 1;
      const voice = pickVoice(line.speaker);
      if (voice) utterance.voice = voice;
      spokenWord = -1;
      renderWords(line, spokenWord);
      utterance.onboundary = (ev) => {{
        if (ev.name !== 'word') return;
        spokenWord += 1;
        renderWords(line, spokenWord);
      }};
      utterance.onstart = () => {{
        if (playStatus) playStatus.textContent = 'Speaking… watch the highlighted panel';
      }};
      utterance.onend = () => {{
        btnPlay.disabled = false;
        btnPause.disabled = true;
        if (lineIndex < lines.length - 1) {{
          spokenWord = -1;
          setLine(lineIndex + 1);
          speakCurrent();
        }} else if (playStatus) {{
          playStatus.textContent = 'Finished — use Prev/Next or Play again';
        }}
      }};
      if (!('speechSynthesis' in window) && playStatus) {{
        playStatus.textContent = 'Voice unavailable in this browser — use timeline to step lines';
      }}
      speechSynthesis.speak(utterance);
      btnPlay.disabled = true;
      btnPause.disabled = false;
    }}

    function stopSpeech() {{
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      utterance = null;
      btnPlay.disabled = false;
      btnPause.disabled = true;
    }}

    btnPlay.addEventListener('click', () => {{ setLine(lineIndex); speakCurrent(); }});
    btnPause.addEventListener('click', stopSpeech);
    btnPrev.addEventListener('click', () => {{ stopSpeech(); spokenWord = -1; setLine(lineIndex - 1); }});
    btnNext.addEventListener('click', () => {{ stopSpeech(); spokenWord = -1; setLine(lineIndex + 1); }});

    if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {{}};
    if (lines.length) setLine(0);
  }})();
  </script>
</body>
</html>"""

    output.write_text(body, encoding="utf-8")
    return output