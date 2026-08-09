"""lookBOOK — Shot-to-Animatic Generator (M5)

Reads a lookBOOK shot graph JSON and generates a low-fidelity animatic MP4:
  - One synthetic clip per shot (3–5 s)
  - Shot metadata and MPT-style prompt overlay
  - Simple camera-motion simulation (pan, zoom, tilt)
  - Concatenated into a single preview video

Dependencies: moviepy (already used by the MoneyPrinterTurbo submodule).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..models import write_json
from ..pipeline.common import resolve_shot_graph
from ..schemas import ShotGraph

# ---------------------------------------------------------------------------
# Optional moviepy import — fail gracefully with a clear message
# ---------------------------------------------------------------------------
try:
    from moviepy import (
        ColorClip,
        CompositeVideoClip,
        TextClip,
        concatenate_videoclips,
        vfx,
    )

    _MOVIEPY = True
except Exception as exc:  # pragma: no cover
    _MOVIEPY = False
    _MOVIEPY_ERR = exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CLIP_DURATION: float = 3.0
DEFAULT_WIDTH: int = 640
DEFAULT_HEIGHT: int = 360
DEFAULT_FPS: int = 24

TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "establishing": (30, 60, 90),
    "dialogue": (60, 90, 30),
    "action": (90, 30, 30),
    "transition": (60, 30, 90),
    "closeup": (90, 60, 30),
    "wide": (30, 90, 60),
}

TYPE_DEFAULT_COLOR: tuple[int, int, int] = (45, 45, 45)

_FONT_CANDIDATES: list[str] = [
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

def _resolve_font() -> str | None:
    """Return the first usable TTF path, or *None* if none is found."""
    for candidate in _FONT_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            return str(p)
    return None


# ---------------------------------------------------------------------------
# Shot → MPT prompt
# ---------------------------------------------------------------------------

def shot_to_mpt_prompt(shot: dict[str, Any]) -> str:
    """Convert a lookBOOK shot dict into a MoneyPrinterTurbo-style prompt."""
    parts: list[str] = []

    shot_type = shot.get("type", "establishing")
    camera = shot.get("camera", "static")
    motion = shot.get("motion_directive", "")
    dialogue = " ".join(shot.get("dialogue", []))
    narration = " ".join(shot.get("narration", []))
    characters = shot.get("characters", [])

    parts.append(f"{shot_type.replace('_', ' ').title()} shot")
    if camera != "static":
        parts.append(f"Camera: {camera}")
    if characters:
        parts.append(f"Characters: {', '.join(characters)}")
    if dialogue:
        parts.append(f"Dialogue: {dialogue[:120]}")
    if narration:
        parts.append(f"Narration: {narration[:120]}")
    if motion:
        parts.append(f"Motion: {motion[:120]}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Synthetic clip generation
# ---------------------------------------------------------------------------

def _camera_motion_clip(
    clip: TextClip,
    camera: str,
    duration: float,
    width: int,
    height: int,
) -> TextClip:
    """Apply a simple motion effect to *clip* based on the camera directive."""
    camera_norm = camera.lower().strip()

    # Pan / track — horizontal translation
    if camera_norm in ("pan right", "track right"):
        return clip.with_position(
            lambda t: (-width * 0.15 * (t / duration), "center")
        )
    if camera_norm in ("pan left", "track left"):
        return clip.with_position(
            lambda t: (width * 0.15 * (t / duration), "center")
        )

    # Tilt — vertical translation
    if camera_norm in ("tilt up", "crane up"):
        return clip.with_position(
            lambda t: ("center", height * 0.15 * (t / duration))
        )
    if camera_norm in ("tilt down", "crane down"):
        return clip.with_position(
            lambda t: ("center", -height * 0.15 * (t / duration))
        )

    # Zoom / dolly — scale
    if camera_norm in ("zoom in", "dolly in", "push in"):
        return clip.with_effects(
            [vfx.Resize(lambda t: 1.0 + 0.25 * (t / duration))]
        )
    if camera_norm in ("zoom out", "dolly out", "pull out"):
        return clip.with_effects(
            [vfx.Resize(lambda t: 1.25 - 0.25 * (t / duration))]
        )

    # Default — static
    return clip


def generate_shot_clip(
    shot: dict[str, Any],
    output_path: str | Path,
    *,
    duration: float = DEFAULT_CLIP_DURATION,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    font_path: str | None = None,
) -> Path:
    """Render a single synthetic animatic clip for *shot*.

    The clip contains:
      • A coloured background keyed by shot type
      • The MPT prompt as a caption
      • A bold shot-number overlay
      • A simple camera-motion simulation (pan, zoom, tilt)

    Returns the path to the written MP4.
    """
    if not _MOVIEPY:
        raise RuntimeError(
            f"moviepy is required for animatic generation ({_MOVIEPY_ERR})"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    font = font_path or _resolve_font()
    if font is None:
        raise RuntimeError(
            "No usable TTF font found. Install a system font or pass font_path."
        )

    shot_index = shot.get("shot_index", 0)
    shot_type = shot.get("type", "establishing")
    camera = shot.get("camera", "static")
    color = TYPE_COLORS.get(shot_type, TYPE_DEFAULT_COLOR)

    mpt_prompt = shot_to_mpt_prompt(shot)

    # Background
    bg = ColorClip(size=(width, height), color=color, duration=duration)

    # Prompt caption (main body text)
    body_text = (
        f"{mpt_prompt}\n\n"
        f"Type: {shot_type} | Camera: {camera} | Duration: {duration:.1f}s"
    )
    try:
        prompt_clip = TextClip(
            text=body_text,
            font=font,
            font_size=18,
            color="white",
            stroke_color="black",
            stroke_width=1,
            size=(width - 40, height - 80),
            text_align="center",
            vertical_align="center",
            method="caption",
        )
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            f"Invalid font {font}: {exc}"
        ) from exc
    prompt_clip = _camera_motion_clip(prompt_clip, camera, duration, width, height)
    prompt_clip = prompt_clip.with_duration(duration)

    # Shot-number badge (top-centre)
    badge = TextClip(
        text=f"SHOT {shot_index:03d}",
        font=font,
        font_size=36,
        color="white",
        stroke_color="black",
        stroke_width=2,
        size=(width, height),
        text_align="center",
        vertical_align="top",
        margin=(0, 16),
    ).with_duration(duration)

    # Composite layers
    composite = CompositeVideoClip(
        [bg, prompt_clip, badge],
        size=(width, height),
    ).with_duration(duration)

    composite.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio=False,
        logger=None,
    )
    return output_path


# ---------------------------------------------------------------------------
# Full animatic assembly
# ---------------------------------------------------------------------------

def build_animatic(
    shot_graph_path: str | Path,
    output_path: str | Path,
    *,
    clip_duration: float = DEFAULT_CLIP_DURATION,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    font_path: str | None = None,
    keep_clips: bool = False,
    temp_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build an animatic MP4 from a lookBOOK shot-graph JSON.

    Parameters
    ----------
    shot_graph_path:
        Path to a *shot_graph.json* (classical or vision-enhanced).
    output_path:
        Destination MP4 path.
    clip_duration:
        Duration of each synthetic shot clip (seconds).
    width, height, fps:
        Video dimensions and frame rate.
    font_path:
        Optional explicit path to a TTF font.
    keep_clips:
        If *True*, retain the per-shot intermediate MP4s.
    temp_dir:
        Directory for intermediate clips (defaults to a temp folder).

    Returns
    -------
    A dict with metadata including ``output_path``, ``total_shots``,
    ``total_duration_seconds``, and ``clips``.
    """
    if not _MOVIEPY:
        raise RuntimeError(
            f"moviepy is required for animatic generation ({_MOVIEPY_ERR})"
        )

    shot_graph_path = Path(shot_graph_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _, shot_data = resolve_shot_graph(Path("."), shot_graph_path)

    # Validate schema version if present (be lenient)
    schema = shot_data.get("schema", "")
    if schema and not schema.startswith("lookbook.shot_graph"):
        raise ValueError(f"Unrecognised shot graph schema: {schema}")

    shots = shot_data.get("shots", [])
    if not shots:
        raise ValueError("No shots found in shot graph.")

    work_dir = Path(temp_dir) if temp_dir else Path(output_path).parent / ".animatic_clips"
    work_dir.mkdir(parents=True, exist_ok=True)

    clips_info: list[dict[str, Any]] = []
    video_clips = []

    for shot in shots:
        shot_index = shot.get("shot_index", 0)
        clip_path = work_dir / f"shot_{shot_index:03d}.mp4"

        generate_shot_clip(
            shot,
            clip_path,
            duration=clip_duration,
            width=width,
            height=height,
            fps=fps,
            font_path=font_path,
        )

        # Reload the written clip so moviepy handles timing correctly
        from moviepy import VideoFileClip

        vc = VideoFileClip(str(clip_path))
        video_clips.append(vc)
        clips_info.append(
            {
                "shot_index": shot_index,
                "clip_path": str(clip_path),
                "duration": clip_duration,
                "prompt": shot_to_mpt_prompt(shot),
            }
        )

    # Concatenate
    final = concatenate_videoclips(video_clips, method="compose")
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio=False,
        logger=None,
    )
    final.close()
    for vc in video_clips:
        vc.close()

    # Clean up intermediate clips unless requested
    if not keep_clips:
        for info in clips_info:
            Path(info["clip_path"]).unlink(missing_ok=True)
        # Remove work dir if empty
        try:
            work_dir.rmdir()
        except OSError:
            pass

    total_duration = len(shots) * clip_duration
    result = {
        "schema": "lookbook.animatic.v0.1",
        "output_path": str(output_path),
        "total_shots": len(shots),
        "total_duration_seconds": total_duration,
        "fps": fps,
        "width": width,
        "height": height,
        "clip_duration": clip_duration,
        "clips": clips_info,
    }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m lookbook.video.animatic",
        description="Generate a low-fidelity animatic MP4 from a lookBOOK shot graph.",
    )
    parser.add_argument("shot_graph", help="Path to shot_graph.json")
    parser.add_argument("--output", "-o", required=True, help="Output MP4 path")
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_CLIP_DURATION,
        help=f"Seconds per shot (default {DEFAULT_CLIP_DURATION})",
    )
    parser.add_argument(
        "--width", type=int, default=DEFAULT_WIDTH, help=f"Width (default {DEFAULT_WIDTH})"
    )
    parser.add_argument(
        "--height", type=int, default=DEFAULT_HEIGHT, help=f"Height (default {DEFAULT_HEIGHT})"
    )
    parser.add_argument(
        "--fps", type=int, default=DEFAULT_FPS, help=f"FPS (default {DEFAULT_FPS})"
    )
    parser.add_argument("--font", default=None, help="Path to a TTF font")
    parser.add_argument("--keep-clips", action="store_true", help="Keep intermediate shot MP4s")

    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    main()
