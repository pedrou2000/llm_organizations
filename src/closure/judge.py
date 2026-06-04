"""LLM-as-a-judge for math-answer equivalence.

Single source of truth for "is candidate equivalent to gold?" Used by the
verify-tool, the substrate sanity check, and the final-correct check in
trial runners. Same judge model across all probed models so we don't
introduce a probe ↔ judge confound.
"""
from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from .models import MODELS

JUDGE_MODEL_LABEL = "haiku-4.5"

JUDGE_SYSTEM_PROMPT = (
    "You are a math grader. Decide whether the CANDIDATE answer is "
    "mathematically equivalent to the GOLD answer.\n\n"
    "Treat as EQUIVALENT:\n"
    "- Different notations of the same value: 2 sqrt(5) ≡ 2*sqrt(5) ≡ "
    "2 \\sqrt{5} ≡ \\sqrt{20}.\n"
    "- Algebraic rearrangements of the same expression: ((k+1)/k)^k ≡ "
    "(1 + 1/k)^k.\n"
    "- Different fraction forms: 17/1900 ≡ \\frac{17}{1900}.\n"
    "- Boxed vs unboxed: \\boxed{42} ≡ 42.\n"
    "- Different symbolic forms of a multi-variable answer: p^a q^b r^c "
    "≡ p**a * q**b * r**c ≡ (p^a)(q^b)(r^c).\n\n"
    "Treat as NOT EQUIVALENT:\n"
    "- Numerically different values.\n"
    "- Candidate gives only part of a multi-part answer "
    "(e.g., gold says 'the assertion is false; n=25 is a counter-example' "
    "but candidate just says '25' with no context).\n"
    "- Candidate gives a number when gold requires a yes/no or descriptive "
    "answer.\n"
    "- Candidate is a proof outline, restatement of the problem, or words "
    "like 'Proved' / 'QED' rather than a final answer.\n"
    "- Candidate is empty or non-mathematical.\n\n"
    "Reply with EXACTLY one word: YES or NO. No explanation."
)


def _judge_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELS[JUDGE_MODEL_LABEL],
        setting_sources=[],
        strict_mcp_config=True,
        mcp_servers={},
        allowed_tools=[],
        permission_mode="bypassPermissions",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        max_turns=1,
    )


async def judge_correct(gold: str, candidate: str | None) -> bool:
    """Judge whether `candidate` is mathematically equivalent to `gold`.

    - Returns True iff the model emits 'YES'.
    - Returns False on empty/None candidate, model error, or any non-YES output.
    - Fast-path: exact-string match short-circuits the call.
    """
    if not isinstance(gold, str) or not isinstance(candidate, str):
        return False
    if not candidate.strip():
        return False
    if gold.strip() == candidate.strip():
        return True

    user_msg = f"GOLD ANSWER:\n{gold}\n\nCANDIDATE ANSWER:\n{candidate}"
    final_text = ""
    try:
        async for msg in query(prompt=user_msg, options=_judge_options()):
            if isinstance(msg, AssistantMessage):
                for blk in msg.content:
                    if isinstance(blk, TextBlock):
                        final_text += blk.text
    except Exception:
        return False

    txt = final_text.strip().upper().strip(".,!?\"'`*")
    if txt == "YES":
        return True
    if txt == "NO":
        return False
    # Defensive: model violated single-word instruction. Default False
    # (safer to under-credit than over-credit). If you see many of these,
    # tighten the prompt.
    return False
