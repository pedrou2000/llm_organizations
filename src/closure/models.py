"""Bedrock model IDs used across closure-bias probes.

Cross-region inference profile prefix (us.) is required.
Haiku 3 is excluded: it predates prompt caching, which the Claude Code CLI
always sends, so every request is rejected with a 400 by Bedrock.

IDs verified by direct invoke_model probe against us-east-1 (2026-06-02).
"""

MODELS: dict[str, str] = {
    "haiku-3.5":  "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "haiku-4.5":  "us.anthropic.claude-haiku-4-5-20251001-v1:0",

    "sonnet-4":   "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "sonnet-4.5": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet-4.6": "us.anthropic.claude-sonnet-4-6",

    "opus-4.5":   "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "opus-4.6":   "us.anthropic.claude-opus-4-6-v1",
    "opus-4.7":   "us.anthropic.claude-opus-4-7",
    "opus-4.8":   "us.anthropic.claude-opus-4-8",
}


def label_for_id(model_id: str) -> str | None:
    """Reverse lookup: get the short label (haiku-4.5) for a Bedrock ID."""
    for k, v in MODELS.items():
        if v == model_id:
            return k
    return None
