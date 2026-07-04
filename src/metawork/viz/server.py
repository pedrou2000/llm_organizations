"""FastAPI app for the trajectory visualizer: gallery + per-trajectory pages.

Routing only — everything else lives in the package: action semantics/colors in
`actions`, per-trajectory shaping in `stats`, display formatting in `format`.
Reads trials fresh from disk on each request (cheap; a job has a few dozen
trials), so newly-generated trajectories appear on refresh with no restart.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import actions
from .format import FMT
from .judgement import load_judgement, overall_gap_for
from .loader import DEFAULT_JOBS_DIR, discover_trials, load_by_key
from .stats import shape_step, summarize

_TEMPLATES = Path(__file__).with_name("templates")


def create_app(jobs_dir: Path | str = DEFAULT_JOBS_DIR) -> FastAPI:
    app = FastAPI(title="meta-work trajectory viz")
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    # Globals every template shares: formatters (`fmt`), kind colors as CSS
    # vars (`kind_css`), and the filter-chip vocabulary (`kinds`).
    env.globals.update(fmt=FMT, kind_css=actions.css_vars(), kinds=actions.KINDS)

    @app.get("/", response_class=HTMLResponse)
    def gallery():
        cards = [summarize(t) for t in discover_trials(jobs_dir)]
        # meta-work overall_gap per card (None if the trial hasn't been judged)
        gaps = {c.key: overall_gap_for(c.key) for c in cards}
        jobs = sorted({c.job for c in cards})
        return env.get_template("gallery.html").render(cards=cards, jobs=jobs, gaps=gaps)

    @app.get("/trial/{job}/{trial_id}", response_class=HTMLResponse)
    def trial(job: str, trial_id: str):
        t = load_by_key(f"{job}/{trial_id}", jobs_dir)
        if t is None:
            raise HTTPException(404, f"no trial {job}/{trial_id}")
        s = summarize(t)
        steps = [shape_step(raw) for raw in t.steps]
        judgement = load_judgement(f"{job}/{trial_id}", max_step=len(t.steps))
        return env.get_template("trajectory.html").render(
            s=s, steps=steps, judgement=judgement)

    return app
