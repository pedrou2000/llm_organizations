"""FastAPI app for the trajectory visualizer: gallery + per-trajectory pages.

Run via `scripts/metawork/viz.py`. Reads trials fresh from disk on each request
(cheap; a job has a few dozen trials), so newly-generated trajectories appear on
refresh with no restart.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .loader import DEFAULT_JOBS_DIR, discover_trials, load_by_key
from .stats import shape_step, summarize

_TEMPLATES = Path(__file__).with_name("templates")

# Categorical colors for action kinds (match base.html --k-* vars).
_KIND_COLOR = {
    "prose": "#8b93a3", "exec": "#4f8ff7", "patch": "#f2a541",
    "plan": "#4fd1a5", "other": "#c98bdb",
}
_TOOL_KIND = {  # function_name -> kind (for the histogram)
    "exec_command": "exec", "write_stdin": "exec",
    "apply_patch": "patch", "update_plan": "plan",
}


# ---------- template formatting helpers (exposed to Jinja as `f`) ----------


class _Fmt:
    @staticmethod
    def pct(x):
        return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "–"

    @staticmethod
    def pctfrac(x):
        return f"{x*100:.0f}%" if isinstance(x, (int, float)) else "–"

    @staticmethod
    def k(n):
        if not isinstance(n, (int, float)):
            return "–"
        return f"{n/1e6:.1f}M" if n >= 1e6 else (f"{n/1e3:.0f}K" if n >= 1e3 else str(int(n)))

    @staticmethod
    def dur(sec):
        if not isinstance(sec, (int, float)):
            return "–"
        m, s = divmod(int(sec), 60)
        return f"{m}m {s}s" if m else f"{s}s"

    @staticmethod
    def cls(x):
        if not isinstance(x, (int, float)):
            return ""
        return "good" if x >= 0.6 else ("mid" if x >= 0.3 else "low")


def _score_card(s: dict) -> dict:
    """Gallery-card view derived from a summary."""
    f = _Fmt()
    fw = s["first_write_frac"]
    return {
        **s,
        "ux_fmt": f.pct(s["ux"]), "ux_cls": f.cls(s["ux"]),
        "partial_fmt": f.pct(s["partial"]), "partial_cls": f.cls(s["partial"]),
        "partial_pct": (s["partial"] * 100) if isinstance(s["partial"], (int, float)) else 0,
        "first_write_pct": (f"{fw*100:.0f}%" if isinstance(fw, (int, float)) else "–"),
    }


def _hist_bars(action_hist: dict) -> list[tuple]:
    """(name, count, color, width%) per action kind, aggregated for the bar."""
    by_kind: dict[str, int] = {}
    for fn, cnt in action_hist.items():
        by_kind[_TOOL_KIND.get(fn, "other")] = by_kind.get(_TOOL_KIND.get(fn, "other"), 0) + cnt
    total = sum(by_kind.values()) or 1
    order = ["exec", "patch", "plan", "other"]
    return [(k, by_kind[k], _KIND_COLOR[k], 100 * by_kind[k] / total)
            for k in order if by_kind.get(k)]


def create_app(jobs_dir: Path | str = DEFAULT_JOBS_DIR) -> FastAPI:
    app = FastAPI(title="meta-work trajectory viz")
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    fmt = _Fmt()

    @app.get("/", response_class=HTMLResponse)
    def gallery():
        trials = discover_trials(jobs_dir)
        cards = [_score_card(summarize(t)) for t in trials]
        jobs = sorted({c["job"] for c in cards})
        return env.get_template("gallery.html").render(cards=cards, jobs=jobs)

    @app.get("/trial/{job}/{trial_id}", response_class=HTMLResponse)
    def trial(job: str, trial_id: str):
        t = load_by_key(f"{job}/{trial_id}", jobs_dir)
        if t is None:
            raise HTTPException(404, f"no trial {job}/{trial_id}")
        s = summarize(t)
        steps = []
        for raw in t.steps:
            sh = shape_step(raw)
            sh["msg_preview"] = (sh["message"][:90] + "…") if len(sh["message"]) > 90 else sh["message"]
            sh["hay"] = (sh["message"] + " " + sh["action"] + " " + sh["observation"]).lower()[:4000]
            steps.append(sh)
        return env.get_template("trajectory.html").render(
            s=s, steps=steps, f=fmt, hist_bars=_hist_bars(s["action_hist"]),
        )

    return app
