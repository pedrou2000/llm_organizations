"""Source A: the published SWE-Marathon website corpus (observational study).

Downloads published trajectories and judges them. Kept for the observational
analysis (its outputs back the figures in scripts/metawork/plot.py); the
nudge experiment from M4 onward uses `metawork.harbor` instead.
"""
from .harvest import SIZES, harvest
from .judge_corpus import judge_corpus

__all__ = ["SIZES", "harvest", "judge_corpus"]
