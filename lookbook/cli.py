from __future__ import annotations
import argparse
import json
import logging
import shutil
import sys
import traceback
from pathlib import Path
from .project import init_project
from .pipeline.analyze import analyze_source
from .pipeline.true_animation_packet import create_true_animation_packet
from .pipeline.export_web import export_web
from .pipeline.ocr import extract_text
from .pipeline.panels import detect_panels
from .pipeline.characters import extract_characters
from .pipeline.scene_graph import build_scene_graph
from .pipeline.shot_graph import build_shot_graph
from .pipeline.choreography import build_choreography
from .pipeline.living_panels_export import export_living_panels
from .pipeline.runway_export import export_runway
from .pipeline.veo_export import export_veo
from .pipeline.kling_export import export_kling
from .pipeline.comfyui_export import export_comfyui
from .pipeline.ffmpeg_export import export_ffmpeg
from .pipeline.remotion_export import export_remotion
from .pipeline.cineforge_export import CineforgeIngestError, export_cineforge
from .pipeline.vault_import import import_vault_manifest
from .pipeline.archive import list_pages, process_archive
from .pipeline.vision_enhanced import (
    analyze_source_vision,
    extract_characters_vision,
    build_scene_graph_vision,
    build_shot_graph_vision,
)
from .pipeline.vision_cache import VisionCache
from .pipeline.director_ai import export_director_packet
from .pipeline.docs_export import export_docs
from .lab import install_demo_lab
from .lab_server import run_lab_server
from .telemetry import session_summary
from .video.animatic import build_animatic

logger = logging.getLogger("lookbook.cli")


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    log_level_env = __import__("os").environ.get("LOG_LEVEL", "").upper()
    if log_level_env:
        level = getattr(logging, log_level_env, level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _handle_errors(func):
    """Decorator that wraps a CLI command handler with user-friendly error handling."""

    def wrapper(args):
        verbose = getattr(args, "verbose", False)
        _setup_logging(verbose)
        try:
            func(args)
        except SystemExit:
            raise
        except FileNotFoundError as exc:
            logger.error("Not found: %s", exc)
            if verbose:
                traceback.print_exc()
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(3)
        except NotADirectoryError as exc:
            logger.error("Not found: %s", exc)
            if verbose:
                traceback.print_exc()
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(3)
        except PermissionError as exc:
            logger.error("Permission denied: %s", exc)
            if verbose:
                traceback.print_exc()
            print(f"Error: permission denied — {exc}", file=sys.stderr)
            sys.exit(4)
        except Exception as exc:
            logger.exception("Unhandled error in %s", func.__name__)
            if verbose:
                traceback.print_exc()
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    return wrapper


@_handle_errors
def cmd_init(args):
    print(f"Created lookBOOK project: {init_project(args.path, args.name)}")


@_handle_errors
def cmd_import_vault(args):
    manifest = Path(args.manifest)
    if not manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest}")
    result = import_vault_manifest(
        args.project,
        manifest,
        init_if_missing=not args.no_init,
        project_name=args.name,
    )
    print(f"Vault import complete: {result['files_written']} file(s)")
    print(f"  Project: {result['project']}")
    print(f"  Record: {result['record_path']}")
    for item in result.get("written", []):
        print(f"  Source: {item['path']}")


@_handle_errors
def cmd_analyze(args):
    project = Path(args.project)
    source = Path(args.source)
    if not project.exists():
        init_project(project, project.name)
    target = project / "source" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    payload = analyze_source(target, project)
    print(f"Analysis written: {project / 'analysis' / 'source_analysis.json'}")
    if "image" in payload:
        print(f"Detected image: {payload['image']['width']}x{payload['image']['height']}")


@_handle_errors
def cmd_true_animation_packet(args):
    print(
        f"Created true-animation packet: {create_true_animation_packet(args.project, args.target)}"
    )


@_handle_errors
def cmd_export_web(args):
    print(f"Exported review HTML: {export_web(args.project, args.output)}")


@_handle_errors
def cmd_demo(args):
    project = init_project(args.path, "lookBOOK Vector Bay 7 Demo")
    create_true_animation_packet(project, "runway")
    export_web(project, project / "exports" / "review.html")
    print(f"Created demo project: {project}")


@_handle_errors
def cmd_install_demo_lab(args):
    print(f"Installed demo lab: {install_demo_lab(args.output)}")


@_handle_errors
def cmd_lab_server(args):
    run_lab_server(port=args.port)


@_handle_errors
def cmd_director_ai(args):
    path = export_director_packet(args.project, target=args.target)
    print(f"Director AI packet exported: {path}")


@_handle_errors
def cmd_director_graph_run(args):
    from .director_graph_client import probe_director_graph, run_director_graph
    from .models import write_json
    from pathlib import Path

    probe = probe_director_graph()
    if not probe.get("online"):
        raise RuntimeError(
            "Director graph sidecar offline — run: python director-graph/server.py"
        )
    project = Path(args.project)
    result = run_director_graph(
        str(project.resolve()),
        profile_id=args.profile,
        auto_approve=not args.no_approve,
        dry_run=args.dry_run,
        target=args.target,
    )
    review = (result.get("state") or {}).get("review_summary") or {}
    write_json(
        project / "analysis" / "director_graph_run.json",
        {
            "schema": "lookbook.director_graph_run.v1",
            "ok": bool(result.get("ok")),
            "profile_id": args.profile,
            "dry_run": args.dry_run,
            "review_summary": review,
            "error": result.get("error"),
        },
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "director graph run failed")
    print(f"Director graph OK — profile {args.profile}")
    print(f"  Shots: {review.get('shot_count', '?')}")
    if review.get("exports"):
        print(f"  Exports: {json.dumps(review['exports'], default=str)}")


@_handle_errors
def cmd_telemetry(args):
    stats = session_summary()
    print(f"Session: {stats['session']}")
    print(f"  Events: {stats['events']}")
    print(f"  Vision calls: {stats['vision_calls']}")
    print(f"  Vision cost: ~${stats['vision_cost_usd']} USD")
    print(f"  Cache hits/misses: {stats['cache_hits']}/{stats['cache_misses']}")
    if stats['exports']:
        print("  Exports:")
        for platform, count in stats['exports'].items():
            print(f"    {platform}: {count}")


@_handle_errors
def cmd_export_docs(args):
    path = export_docs(args.project, output_name=args.output)
    print(f"Exported news & docs page: {path}")


@_handle_errors
def cmd_extract_text(args):
    blocks = extract_text(
        args.source,
        args.project,
        lang=args.lang,
        psm=args.psm,
        preprocess=not args.no_preprocess,
    )
    print(f"Extracted {len(blocks)} text blocks → project/analysis/ocr_result.json")
    for b in blocks[:5]:
        print(f"  [{b['classification']}] {b['text'][:60]}")
    if len(blocks) > 5:
        print(f"  ... and {len(blocks) - 5} more")


@_handle_errors
def cmd_detect_panels(args):
    panels = detect_panels(args.source, args.project)
    print(f"Detected {len(panels)} panels → project/analysis/panel_analysis.json")
    for p in panels[:5]:
        print(f"  Panel {p['panel_index']}: {p['bbox']}")
    if len(panels) > 5:
        print(f"  ... and {len(panels) - 5} more")


@_handle_errors
def cmd_extract_characters(args):
    if args.use_vision:
        chars = extract_characters_vision(args.project, provider=args.vision_provider)
        path = Path(args.project) / "analysis" / "character_analysis_vision.json"
        print(f"Extracted {len(chars)} vision characters → {path}")
        cost = path.read_text(encoding="utf-8") if path.exists() else "{}"
        cost_data = __import__("json").loads(cost)
        print(f"  Vision calls: {cost_data.get('vision_calls', '?')}, cost: ~${cost_data.get('vision_cost_usd', '?')} USD")
    else:
        chars = extract_characters(args.source, args.project, similarity_threshold=args.threshold)
        print(f"Extracted {len(chars)} character clusters → project/analysis/character_analysis.json")
    for c in chars[:5]:
        print(f"  {c.get('character_id', c.get('name', '?'))}: {c['appearances']} appearances")
    if len(chars) > 5:
        print(f"  ... and {len(chars) - 5} more")


@_handle_errors
def cmd_build_scene_graph(args):
    if args.use_vision:
        scenes = build_scene_graph_vision(args.project, provider=args.vision_provider)
        path = Path(args.project) / "analysis" / "scene_graph_vision.json"
        print(f"Built {len(scenes)} vision scenes → {path}")
    else:
        scenes = build_scene_graph(args.project)
        print(f"Built {len(scenes)} scenes → project/analysis/scene_graph.json")
    for s in scenes:
        print(
            f"  Scene {s['scene_index']}: {s['panel_count']} panels, {len(s.get('characters', []))} characters"
        )


@_handle_errors
def cmd_build_choreography(args):
    lines = build_choreography(args.project)
    print(f"Built {len(lines)} choreography lines → project/analysis/choreography.json")
    for ln in lines[:5]:
        print(f"  Line {ln['line_index']}: {ln['speaker']} · panel {ln['panel_index']} — {ln['text'][:60]}")
    if len(lines) > 5:
        print(f"  ... and {len(lines) - 5} more")


@_handle_errors
def cmd_export_living_panels(args):
    out = export_living_panels(args.project, output=args.output)
    print(f"Living panels review → {out}")


@_handle_errors
def cmd_build_shot_graph(args):
    if args.use_vision:
        shots = build_shot_graph_vision(args.project, provider=args.vision_provider)
        path = Path(args.project) / "analysis" / "shot_graph_vision.json"
        print(f"Built {len(shots)} vision shots → {path}")
    else:
        shots = build_shot_graph(args.project)
        print(f"Built {len(shots)} shots → project/analysis/shot_graph.json")
    if shots:
        total_dur = sum(s["duration_seconds"] for s in shots)
        print(f"  Total duration: {total_dur:.1f}s @ 24fps = {int(total_dur * 24)} frames")
        for s in shots[:5]:
            print(
                f"  Shot {s['shot_index']}: {s['type']} ({s['duration_seconds']}s) — {s.get('camera', 'N/A')}"
            )


@_handle_errors
def cmd_vision_cache(args):
    cache = VisionCache(Path(args.project) / "analysis" / "vision_cache")
    if args.clear:
        n = cache.clear()
        print(f"Cleared {n} cached vision entries")
    else:
        stats = cache.stats()
        print(f"Vision cache: {stats['entries']} entries, {stats['total_size_bytes'] / 1024:.1f} KB")


@_handle_errors
def cmd_analyze_vision(args):
    result = analyze_source_vision(args.source, args.project, provider=args.vision_provider)
    print("Vision analysis complete → project/analysis/source_analysis_vision.json")
    print(result.get("description", "")[:500])
    print(f"\nCost: ~${result.get('cost_usd', '?')} USD")


@_handle_errors
def cmd_export_runway(args):
    jobs = export_runway(args.project)
    print(f"Exported {len(jobs)} Runway jobs → project/exports/runway/")
    for j in jobs[:3]:
        print(f"  Shot {j['shot_index']}: {j['type']} ({j['duration_seconds']}s)")
    if len(jobs) > 3:
        print(f"  ... and {len(jobs) - 3} more")


@_handle_errors
def cmd_export_veo(args):
    prompts = export_veo(args.project)
    print(f"Exported {len(prompts)} Veo prompts → project/exports/veo/")
    for p in prompts[:3]:
        print(f"  Shot {p['shot_index']}: {p['type']} ({p['duration_seconds']}s)")
    if len(prompts) > 3:
        print(f"  ... and {len(prompts) - 3} more")


@_handle_errors
def cmd_export_kling(args):
    result = export_kling(args.project)
    for platform, entries in result.items():
        print(f"Exported {len(entries)} {platform} prompts → project/exports/{platform}/")


@_handle_errors
def cmd_export_comfyui(args):
    wfs = export_comfyui(args.project, model=args.model, width=args.width, height=args.height)
    print(f"Exported {len(wfs)} ComfyUI workflows → project/exports/comfyui/")
    print(f"  Model: {args.model}")
    for w in wfs[:3]:
        print(f"  Shot {w['shot_index']}: {w['type']} ({w['duration_seconds']}s)")
    if len(wfs) > 3:
        print(f"  ... and {len(wfs) - 3} more")


@_handle_errors
def cmd_export_ffmpeg(args):
    result = export_ffmpeg(
        args.project,
        input_pattern=args.pattern,
        output_name=args.output,
        fps=args.fps,
    )
    print("Generated FFmpeg assembly → project/exports/ffmpeg/")
    print(f"  Script: {result['assembly_script']}")
    print(f"  Output: {result['output_file']}")
    print(f"  Shots: {result['total_shots']}")


@_handle_errors
def cmd_export_remotion(args):
    result = export_remotion(args.project, fps=args.fps)
    n = result["total_shots"]
    print(f"Generated Remotion project with {n} shots → project/exports/remotion/")
    print(f"  Duration: {result['total_duration_seconds']:.1f}s @ {result['fps']}fps")
    print(f"  Resolution: {result['resolution']['width']}x{result['resolution']['height']}")
    print("  Setup: cd project/exports/remotion/ && npm install && npm start")


@_handle_errors
def cmd_export_cineforge(args):
    try:
        result = export_cineforge(
            args.project,
            output=args.output,
            shot_graph_path=args.shot_graph,
            replace_existing_shots=not args.no_replace,
            push=args.push,
            cineforge_url=args.cineforge_url,
            project_id=args.project_id,
            api_key=args.api_key,
        )
    except CineforgeIngestError as exc:
        print(f"CineForge ingest error: {exc}")
        sys.exit(1)

    print(f"Exported {result['shot_count']} shots → {result['output_path']}")
    print(f"  Source graph: {result['shot_graph_path']}")
    if result.get("pushed"):
        ingest = result.get("ingest_response") or {}
        print(f"  Pushed to: {result.get('cineforge_url')}")
        print(f"  CineForge project: {result.get('cineforge_project_id')}")
        print(f"  Ingested shots: {ingest.get('shot_count', '?')}")
        if ingest.get("treatment_id"):
            print(f"  Treatment: {ingest['treatment_id']}")


@_handle_errors
def cmd_list_pages(args):
    pages = list_pages(args.archive)
    print(f"Found {len(pages)} pages in {Path(args.archive).name}:")
    for p in pages:
        size_kb = p["size_bytes"] / 1024
        print(f"  Page {p['page_index']:03d}: {p['filename']} ({size_kb:.0f}KB)")


@_handle_errors
def cmd_process_archive(args):
    result = process_archive(
        args.archive,
        args.project,
        no_cleanup=args.keep,
        use_vision=args.use_vision,
        vision_provider=args.vision_provider,
        living_panels=args.living_panels,
    )
    print(f"\nDone. Project: {result['project']}")
    print("  Exports ready in project/exports/*/")


@_handle_errors
def cmd_generate_animatic(args):
    result = build_animatic(
        args.shot_graph,
        args.output,
        clip_duration=args.duration,
        width=args.width,
        height=args.height,
        fps=args.fps,
        font_path=args.font,
        keep_clips=args.keep_clips,
    )
    print(f"Animatic generated: {result['output_path']}")
    print(f"  Shots: {result['total_shots']}")
    print(f"  Duration: {result['total_duration_seconds']:.1f}s @ {result['fps']}fps")
    print(f"  Resolution: {result['width']}x{result['height']}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="lookbook",
        description="Open-source book-to-animation compiler.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full tracebacks on errors and set log level to DEBUG",
    )
    sub = parser.add_subparsers(dest="command", required=True, help="Available commands")

    p = sub.add_parser("init", help="Initialize a new lookBOOK project")
    p.add_argument("path", help="Directory path for the new project")
    p.add_argument("--name", default="Untitled lookBOOK Project", help="Project name")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser(
        "import-vault",
        help="Import NOTEtoolsLM lookbook.source_manifest.v1 into project/source/",
    )
    p.add_argument("manifest", help="Path to lookbook.source_manifest.v1 JSON")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--name", default=None, help="Project name when initializing a new directory")
    p.add_argument(
        "--no-init",
        action="store_true",
        help="Fail if project directory does not exist (default: init new project)",
    )
    p.set_defaults(func=cmd_import_vault)

    p = sub.add_parser("analyze-source", help="Analyze a source file and copy it into the project")
    p.add_argument("source", help="Path to the source file")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("true-animation-packet", help="Generate a true-animation packet for a target platform")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--target",
        default="runway",
        choices=["runway", "veo", "gemini", "kling", "pika", "luma"],
        help="Target platform (default: runway)",
    )
    p.set_defaults(func=cmd_true_animation_packet)

    p = sub.add_parser("lab-server", help="Start the lookBOOK demo lab HTTP server")
    p.add_argument("--port", type=int, default=8042, help="Server port (default: 8042)")
    p.set_defaults(func=cmd_lab_server)

    p = sub.add_parser(
        "director-graph-run",
        help="Run director-graph LangGraph sidecar on a project (:7791)",
    )
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--profile",
        default="classical-runway",
        help="Graph profile (default: classical-runway)",
    )
    p.add_argument("--target", default=None, help="Director target override (runway, veo, …)")
    p.add_argument("--dry-run", action="store_true", help="Plan-only dry run (no exports)")
    p.add_argument("--no-approve", action="store_true", help="Require interactive export approval")
    p.set_defaults(func=cmd_director_graph_run)

    p = sub.add_parser("director-ai", help="Export a Director AI decision packet")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--target",
        default="runway",
        choices=["runway", "veo", "kling", "pika", "luma"],
        help="Target platform (default: runway)",
    )
    p.set_defaults(func=cmd_director_ai)

    p = sub.add_parser("telemetry", help="Show session telemetry summary")
    p.set_defaults(func=cmd_telemetry)

    p = sub.add_parser("export-web", help="Export a review HTML page")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("output", help="Output HTML file path")
    p.set_defaults(func=cmd_export_web)

    p = sub.add_parser("demo", help="Create a full demo project")
    p.add_argument("path", help="Directory path for the demo project")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("install-demo-lab", help="Install the browser demo lab files")
    p.add_argument("output", help="Output directory for the demo lab")
    p.set_defaults(func=cmd_install_demo_lab)

    # Phase C — Source Intelligence commands
    p = sub.add_parser("extract-text", help="Extract text from a source image using OCR")
    p.add_argument("source", help="Path to the source image")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--lang", default="eng", help="OCR language (default: eng)")
    p.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode (default: 6)")
    p.add_argument("--no-preprocess", action="store_true", help="Skip image preprocessing")
    p.set_defaults(func=cmd_extract_text)

    p = sub.add_parser("detect-panels", help="Detect comic panels in a source image")
    p.add_argument("source", help="Path to the source image")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_detect_panels)

    p = sub.add_parser("extract-characters", help="Extract characters from panels")
    p.add_argument("source", help="Path to the source image")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--threshold", type=float, default=0.3, help="Similarity threshold (default: 0.3)")
    p.add_argument("--use-vision", action="store_true", help="Use vision LLM instead of perceptual hashing")
    p.add_argument("--vision-provider", default=None, choices=["openai", "claude", "gemini"], help="Vision LLM provider")
    p.set_defaults(func=cmd_extract_characters)

    p = sub.add_parser("build-scene-graph", help="Build a narrative scene graph")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--use-vision", action="store_true", help="Use vision LLM for narrative scene grouping")
    p.add_argument("--vision-provider", default=None, choices=["openai", "claude", "gemini"], help="Vision LLM provider")
    p.set_defaults(func=cmd_build_scene_graph)

    p = sub.add_parser("build-choreography", help="Build speech-driven choreography from OCR + panels")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_build_choreography)

    p = sub.add_parser("export-living-panels", help="Export browser living-panels HTML review")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--output",
        default=None,
        help="Output HTML path (default: project/exports/living_panels/review.html)",
    )
    p.set_defaults(func=cmd_export_living_panels)

    p = sub.add_parser("build-shot-graph", help="Build a director-level shot graph")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--use-vision", action="store_true", help="Use vision LLM for director-level shot analysis")
    p.add_argument("--vision-provider", default=None, choices=["openai", "claude", "gemini"], help="Vision LLM provider")
    p.set_defaults(func=cmd_build_shot_graph)

    p = sub.add_parser("analyze-vision", help="Analyze a source image with a vision LLM")
    p.add_argument("source", help="Path to the source image")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--vision-provider", default=None, choices=["openai", "claude", "gemini"], help="Vision LLM provider")
    p.set_defaults(func=cmd_analyze_vision)

    p = sub.add_parser("vision-cache", help="Show or clear vision LLM cache")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--clear", action="store_true", help="Clear all cached vision results")
    p.set_defaults(func=cmd_vision_cache)

    # Phase D — Generation Integration commands
    p = sub.add_parser("export-runway", help="Export Runway Gen-2 job prompts")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_export_runway)

    p = sub.add_parser("export-veo", help="Export Google Veo prompts")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_export_veo)

    p = sub.add_parser("export-kling", help="Export Kling AI prompts")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.set_defaults(func=cmd_export_kling)

    p = sub.add_parser("export-comfyui", help="Export ComfyUI workflows")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--model", default="realisticVisionV51_v51VAE.safetensors", help="ComfyUI model name")
    p.add_argument("--width", type=int, default=1024, help="Output width (default: 1024)")
    p.add_argument("--height", type=int, default=576, help="Output height (default: 576)")
    p.set_defaults(func=cmd_export_comfyui)

    p = sub.add_parser("export-ffmpeg", help="Export FFmpeg assembly script")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--pattern", default="shot_{index:03d}.mp4", help="Input filename pattern")
    p.add_argument("--output", default="lookbook_assembly.mp4", help="Output filename")
    p.add_argument("--fps", type=int, default=24, help="Frames per second (default: 24)")
    p.set_defaults(func=cmd_export_ffmpeg)

    p = sub.add_parser("export-remotion", help="Export a Remotion project")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument("--fps", type=int, default=24, help="Frames per second (default: 24)")
    p.set_defaults(func=cmd_export_remotion)

    p = sub.add_parser(
        "export-cineforge",
        help="Export shot graph for CineForge ingest (file default; optional live push)",
    )
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: project/exports/cineforge/ingest.json)",
    )
    p.add_argument(
        "--shot-graph",
        default=None,
        help="Path to shot_graph.json (auto-detects vision graph when omitted)",
    )
    p.add_argument(
        "--push",
        action="store_true",
        help="POST ingest payload to a running CineForge API",
    )
    p.add_argument(
        "--cineforge-url",
        default=None,
        help="CineForge API base URL (default: CINEFORGE_URL env or http://127.0.0.1:8000)",
    )
    p.add_argument(
        "--project-id",
        default=None,
        help="CineForge project UUID (required with --push)",
    )
    p.add_argument(
        "--api-key",
        default=None,
        help="Optional X-API-Key header (default: CINEFORGE_API_KEY env)",
    )
    p.add_argument(
        "--no-replace",
        action="store_true",
        help="Set replace_existing_shots=false on ingest",
    )
    p.set_defaults(func=cmd_export_cineforge)

    # Batch archive commands
    p = sub.add_parser("list-pages", help="List pages inside a comic archive")
    p.add_argument("archive", help="Path to the archive file")
    p.set_defaults(func=cmd_list_pages)

    p = sub.add_parser("process-archive", help="Process a comic archive into a lookBOOK project")
    p.add_argument("archive", help="Path to the archive file")
    p.add_argument("project", help="Path to the lookBOOK project directory")
    p.add_argument(
        "--keep",
        action="store_true",
        help="Keep extracted page files after processing",
    )
    p.add_argument("--use-vision", action="store_true", help="Run vision-enhanced pipeline stages")
    p.add_argument("--vision-provider", default=None, choices=["openai", "claude", "gemini"], help="Vision LLM provider")
    p.add_argument(
        "--living-panels",
        action="store_true",
        help="Export living panels review HTML (default: always exported to exports/living_panels/review.html)",
    )
    p.set_defaults(func=cmd_process_archive)

    # M5 — Animatic Generator
    p = sub.add_parser("generate-animatic", help="Generate an animatic MP4 from a shot graph")
    p.add_argument("shot_graph", help="Path to shot_graph.json")
    p.add_argument("--output", "-o", required=True, help="Output MP4 path")
    p.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Seconds per shot (default: 3.0)",
    )
    p.add_argument("--width", type=int, default=640, help="Width in pixels (default: 640)")
    p.add_argument("--height", type=int, default=360, help="Height in pixels (default: 360)")
    p.add_argument("--fps", type=int, default=24, help="FPS (default: 24)")
    p.add_argument("--font", default=None, help="Path to a TTF font")
    p.add_argument("--keep-clips", action="store_true", help="Keep intermediate shot MP4s")
    p.set_defaults(func=cmd_generate_animatic)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
