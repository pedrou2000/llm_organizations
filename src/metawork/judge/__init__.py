"""The durable meta-work judge: blind flat_text in, rubric out.

Shared core of the experiment — both trajectory sources (`metawork.harbor` and
`metawork.published`) feed their flattened text through this judge. It depends
on neither source.
"""
from .judge import DEFAULT_JUDGE_MODEL_LABEL, judge_trajectory

__all__ = ["DEFAULT_JUDGE_MODEL_LABEL", "judge_trajectory"]
