"""HTTP client for lookBOOK director-graph LangGraph sidecar (:7791)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = os.environ.get("DIRECTOR_GRAPH_URL", "http://127.0.0.1:7791")


def probe_director_graph(base_url: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    root = (base_url or DEFAULT_URL).rstrip("/")
    url = f"{root}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {
                "online": body.get("status") == "ok",
                "service": body.get("service"),
                "port": body.get("port"),
                "url": root,
            }
    except Exception as exc:
        return {"online": False, "url": root, "error": str(exc)}


def run_director_graph(
    project_path: str,
    *,
    profile_id: str = "classical-runway",
    auto_approve: bool = True,
    dry_run: bool = False,
    target: str | None = None,
    base_url: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    root = (base_url or DEFAULT_URL).rstrip("/")
    payload: dict[str, Any] = {
        "profile_id": profile_id,
        "project_path": project_path,
        "auto_approve": auto_approve,
        "dry_run": dry_run,
    }
    if target:
        payload["target"] = target
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{root}/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {"ok": False, "error": raw or str(exc)}