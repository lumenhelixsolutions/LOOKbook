# LOOKbook

<p align="center">
  <img src="docs/assets/hero.svg" alt="LOOKbook header" width="100%">
</p>

<p align="center">
  <img src="docs/assets/logo.svg" alt="LOOKbook logo" width="120">
</p>

<h3 align="center">Books to motion.</h3>

<p align="center">Open-source compiler that turns books, comics, and illustrated pages into structured animation projects.</p>

<p align="center">
  <a href="https://lumenhelixlab.github.io/LOOKbook/">Launch Page</a>
  <span> · </span>
  <a href="https://github.com/lumenhelixlab/LOOKbook">GitHub</a>
  <span> · </span>
  <a href="https://lumenhelix.com">LumenHelix</a>
</p>

---

LOOKbook is the LumenHelix open-source compiler for turning books, comics, and illustrated pages into structured animation projects. It extracts characters, preserves scene intent, and emits true image-to-video handoff packets for generative video pipelines.

## Why LOOKbook

- **Preserve creative intent.** Scene graphs and character consistency keep the story coherent across every generated shot.
- **Stay pipeline-agnostic.** Export to Runway, Veo, Kling, Pika, Luma, or local stacks from one source of truth.
- **Own your workflow.** Local-first Python CLI and browser lab. No mandatory cloud, no lock-in.

## Quick start

### macOS / Linux

```bash
git clone https://github.com/lumenhelixlab/LOOKbook.git
cd LOOKbook
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
lookbook demo my-demo
```

### Windows (PowerShell)

```powershell
git clone https://github.com/lumenhelixlab/LOOKbook.git
Set-Location LOOKbook
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
lookbook demo my-demo
```

### Windows (Git Bash / WSL)

```bash
git clone https://github.com/lumenhelixlab/LOOKbook.git
cd LOOKbook
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
lookbook demo my-demo
```

> Tested on Windows 11, macOS Sonoma, Ubuntu 22.04/24.04, and modern mobile browsers.

## Features

| Feature | What it gives you |
|---------|-------------------|
| Source analysis | Ingest books, comics, and illustrated pages and break them into panels, characters, and scene intent. |
| True animation standard | Distinguish motion-comic previews from real animation where bodies, limbs, cloth, and dialogue timing matter. |
| Image-to-video handoff | Export structured shot packets ready for Runway, Veo, Kling, Pika, Luma, and local image-to-video stacks. |
| Demo Lab Gen 2 | A unified pipeline server with OCR, vision interpretation, and a browser review UI on port 8042. |

## Architecture

```
lookBOOK/
├── lookbook/       Python CLI + analysis engine
├── demo-lab/       Browser review lab (port 8042)
├── demo-lab-react/ Ant Design UI
├── examples/       Sample keyframes and prompt packs
└── tools/          MoneyPrinterTurbo bridge
```

## Development

```bash
# Start the unified pipeline lab (stdlib only, port 8042)
python -m lookbook.lab_server
# Optional: OCR / panel detection / vision endpoints need extra deps
# pip install -e ".[lab]"  # Pillow + OpenCV + pytesseract (Tesseract on PATH)
```

The React review UI ships prebuilt in `demo-lab-react/dist/` — open `dist/index.html` in a browser (or serve it with any static file server) while the lab server runs; it talks to the API on port 8042. No npm build step is required. To rebuild from source: `cd demo-lab-react && npm install && npm run build`.

## Roadmap

- [ ] Research-to-story portfolio E2E harness
- [ ] Vault import and Obsidian handoff polish
- [ ] CineForge live API push and review sync

## License

Released under the MIT License. Imported books, scans, artwork, voices, fonts, and generated assets have their own rights considerations.

---

<p align="center">
  <sub>LOOKbook is a <a href="https://lumenhelix.com">LumenHelix</a> project — Applied Symbolic Dynamics & Reversible Computation.</sub>
</p>
