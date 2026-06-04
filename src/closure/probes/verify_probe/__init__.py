"""Verify-probe: operationalizes compulsion-to-closure as the rate at which
a model invokes an available `verify` tool before submitting a final answer.

Three conditions:
  - forced  : prompt says "submit immediately, do not second-guess"; only
              `submit` allowed (note: `verify` is still registered with MCP,
              so leakage is possible — see notebook caveats)
  - neutral : prompt mentions verify is available, may use if useful
  - anti    : prompt requires ALWAYS calling verify before submitting
"""
from .conditions import (
    CONDITIONS,
    Condition,
    DISALLOWED_BUILTINS,
    PROMPT_ANTI_BIAS,
    PROMPT_FORCED_BIAS,
    PROMPT_NEUTRAL,
    SUBSTRATE_OPTIONS_BASE,
    SUBSTRATE_PROMPT,
    options_for,
)
from .tools import PROBE_SERVER, TrialContext
from .trial import VerifyProbe, run_trial, substrate_solve

__all__ = [
    "VerifyProbe",
    "run_trial",
    "substrate_solve",
    "CONDITIONS",
    "Condition",
    "PROBE_SERVER",
    "TrialContext",
    "PROMPT_FORCED_BIAS",
    "PROMPT_NEUTRAL",
    "PROMPT_ANTI_BIAS",
    "SUBSTRATE_PROMPT",
    "SUBSTRATE_OPTIONS_BASE",
    "DISALLOWED_BUILTINS",
    "options_for",
]
