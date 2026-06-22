"""Generic bounded-concurrency async runner with progress/ETA/cost reporting.

Probe- and experiment-agnostic: both the closure math sweep and the metawork
judge fan out their LLM calls through `gather_with_progress`. Lives in `common`
so neither research line depends on the other to get it.
"""
from __future__ import annotations

import asyncio
import time

from .trace import fmt_duration


async def gather_with_progress(
    coros: list,
    *,
    limit: int = 32,
    label: str = "run",
    log_each: bool = False,
    log_fields: tuple[str, ...] = (),
) -> list:
    """Bounded concurrency. Reports progress, ETA, running cost, errors."""
    sem = asyncio.Semaphore(limit)
    total = len(coros)
    done = 0
    cost_sum = 0.0
    err_count = 0
    t0 = time.monotonic()
    results: list = [None] * total

    async def _wrapped(idx, c):
        nonlocal done, cost_sum, err_count
        async with sem:
            err_text = None
            try:
                r = await c
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                r = {"error": err_text, "cost_usd": 0.0}
                err_count += 1
            results[idx] = r
            done += 1
            cost_sum += float(r.get("cost_usd") or 0.0)
            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else float("inf")
            line = (
                f"  [{label}] {done:>4}/{total}  "
                f"elapsed {fmt_duration(elapsed):>10s}  "
                f"eta {fmt_duration(eta):>10s}  "
                f"${cost_sum:>5.2f}  "
                f"err={err_count}"
            )
            if err_text:
                line += f"   ERR: {err_text[:160]}"
            elif log_each and log_fields:
                extras = "  ".join(
                    f"{f}={r.get(f)!r}" if not isinstance(r.get(f), float)
                    else f"{f}={r.get(f):.3f}"
                    for f in log_fields if f in r
                )
                line += "   " + extras
            print(line, flush=True)

    await asyncio.gather(*[_wrapped(i, c) for i, c in enumerate(coros)])
    return results
