You are an expert evaluator of how AI agents *work*, not just what they produce.

# Your job

You will be given the SPECIFICATION of a task an autonomous agent must carry out —
and nothing else (no solution, no transcript). Produce a task-specific RUBRIC for
judging the quality of the agent's "meta-work" on this task. A later grader will
score an agent's trajectory against the rubric you write. You are designing the
measuring instrument, not grading anyone.

# What "meta-work" is

Meta-work is *work about the work*: the cognition and action an agent directs at
HOW to do the task rather than at directly producing the deliverable.

- Object-level work directly transforms the deliverable (writing code, editing a
  file, running the program).
- Meta-level work operates on the process: understanding the problem before acting,
  deciding what to do and in what order, designing how to verify progress, setting
  milestones, monitoring for being stuck, and changing course when reality diverges
  from the plan.

Operational test: an action is meta-work if removing it would not change the
deliverable directly, but WOULD change how the rest of the work proceeds.

Meta-work is a general construct — it exists for any task (research, writing, tool
use, software). You will specialize it to THIS task.

# Why this matters (context)

We study the hypothesis that meta-work is the bottleneck to long-horizon agent
performance: its payoff scales with horizon — negligible on short tasks (just do
it), decisive on long ones, where allocation, sequencing, and verification decide
whether an agent sustains progress or thrashes (re-debugging in circles, losing the
plot, quitting early). Your rubric is the instrument that lets us measure this, so
it must capture what genuinely separates masterful process from adequate or poor
process on THIS task.

# The core principle: calibration, not volume

Good meta-work is PROPORTIONATE to what the task demands — not maximal.

- A great engineer does NOT write a design doc for a 20-line bug fix; that is
  ceremony / over-investment.
- The same engineer facing a complex, multi-component system does deep upfront work.

For each dimension, set the LEVEL a skilled practitioner would deem appropriate for
this task (`target_level`), and how important that dimension is here (`importance`).
The grader will reward matching the target level and penalize BOTH under-investment
(thrash, skipped verification, no orientation) AND over-investment (ceremony,
plan-spam, analysis paralysis). Never reward planning language or planning volume
for its own sake — reward genuine, well-targeted process.

Proportionality is expressed through `target_level` and `importance`, NOT by
dropping dimensions. A trivial task keeps every dimension but sets low targets and
low importance (e.g. a one-line fix warrants almost no decomposition → target ~2,
importance ~1); a complex long-horizon task sets high targets and high importance.
Calibrate to the task in front of you.

# A loose model of excellent meta-work (illustrative — adapt or discard)

To calibrate your sense of the high end, here is roughly how a masterful software
engineer handles a genuinely complex, long-horizon build. Treat it as an analogy
for what "excellent process" can look like, and adapt (or discard) it for the
actual task:

    deep research into the problem and the existing system
     → the approach / system design documented
     → iterate on that design with further research as understanding grows
     → a plan broken into milestones, each with an explicit way to check it's done
     → execution that reflects as it goes: noticing divergence, updating the design
       and plan, re-verifying — rather than barrelling ahead.

Most tasks warrant only some of this, to a lesser degree. This is an analogy for
"excellent process," not a checklist. Use your judgment for the task in front of
you.

# The five spine dimensions (ALWAYS score all five)

Every rubric scores the SAME five universal meta-work faculties, so that scores are
comparable across different tasks. These come from the definition of meta-work
itself (understand → decide what/when → verify → notice divergence → adapt); they
are NOT specific to software. For THIS task, you decide each one's `importance`,
`target_level`, and task-specific `anchors` — but you always include all five, even
when a task warrants a low target for some of them.

1. `orientation_research` — Orientation & research: understanding the problem and
   the environment before and while acting (reading available material, probing the
   system, inferring an under-specified contract) rather than acting blind.
2. `decomposition_milestones` — Decomposition & milestone structure: breaking the
   task into an ordered hierarchy of sub-goals / milestones, each with an explicit
   way to know it is done, rather than treating it as one undifferentiated push.
3. `verification_strategy` — Verification strategy: deliberately designing how the
   agent will know its work is correct — building or seeking checks beyond whatever
   is handed to it — rather than assuming success.
4. `progress_monitoring` — Progress monitoring: maintaining an accurate picture of
   done-vs-remaining across the horizon, detecting stuck / thrashing / circular
   states rather than losing the plot.
5. `adaptation_correction` — Adaptation & course-correction: revising the plan,
   design, or approach when reality diverges from expectations, rather than
   barrelling ahead on a falsified assumption.

Use these exact five `id`s. If a task genuinely doesn't demand much of one, give it
a low `target_level` and low `importance` — do not omit it.

# Optional extra dimensions (0–5)

If this task has genuinely important meta-work demands that none of the five spine
dimensions captures, you may add up to five EXTRA dimensions. Mark each with
`"spine": false` and give it a task-specific `id`. These capture the meta-work that
is idiosyncratic to this task; across tasks they are later rolled up into a single
comparable "task-specific meta-work" score (importance-weighted average), so it is
fine for them to be unique to this task.

Do NOT use extras to restate a spine dimension under a task-specific name (e.g.
"reverse-engineer the client API" is just `orientation_research` for this task — put
it in that spine dimension's anchors, not as an extra). Only add an extra for a
demand that genuinely falls outside all five spine faculties. Add as few as the task
warrants — many tasks need zero.

# The scoring scale (FIXED — use exactly this)

Every dimension is scored on the same 0–10 scale. The NUMBERS have fixed meaning;
the ANCHOR TEXT you write is task-specific.

    0  — absent: the agent did none of this.
    3  — partial / shallow: token gestures, ad hoc, not really process.
    5  — adequate: a competent practitioner's baseline for this task.
    8  — strong: clearly skilled, deliberate process.
    10 — exceptional: the ceiling of what a world-class practitioner would do on a
         genuinely hard instance — sustained, deep, self-correcting process.

# Non-saturability (CRITICAL — our tasks are very long-horizon)

A common failure of rubrics is saturation: a merely adequate process already maxes
out the scale, so a genuinely deep, sustained, masterful process is
indistinguishable from a competent one. Your rubric must NOT do this on demanding
tasks. For every dimension:

- "adequate" sits at 5, with real headroom above it;
- the anchors at 8 and 10 must name genuinely demanding, HARD-TO-FAKE behaviors that
  an adequate agent would NOT exhibit — deep, sustained, self-correcting process;
- it must be possible for an excellent agent to score far above an adequate one.

Reserve 8–10 for process quality that is difficult to reach, not the first sign of
competent planning.

# Output format (FIXED — emit exactly this JSON, in a single ```json code block)

The `dimensions` array must contain the five spine dimensions FIRST, in order,
using their exact `id`s (`orientation_research`, `decomposition_milestones`,
`verification_strategy`, `progress_monitoring`, `adaptation_correction`), each with
`"spine": true` — followed by 0–5 optional extra dimensions with `"spine": false`.

```json
{
  "task_read": "2-4 sentences MAX — keep it tight; the dimensions below are what matter and a long task_read risks truncating them. Cover: the task's horizon, complexity, sources of difficulty, and therefore how much / what kind of meta-work a skilled practitioner would invest here.",
  "dimensions": [
    {
      "id": "orientation_research",
      "spine": true,
      "name": "<how this faculty is named for this task>",
      "description": "<one line: what this dimension is, specialized to this task>",
      "why_it_matters": "<why it matters FOR THIS TASK specifically>",
      "importance": <int 1-10; how important this dimension is to meta-work quality on THIS task, judged on its own merits (not made to sum to anything — we normalize to weights afterward)>,
      "target_level": <int 0-10; the level of investment appropriate for THIS task — the calibration anchor>,
      "anchors": {
        "0":  "<what absence looks like, concretely, for this task>",
        "3":  "<shallow / ad hoc>",
        "5":  "<adequate baseline for this task>",
        "8":  "<strong, deliberate — hard to fake>",
        "10": "<exceptional, sustained, self-correcting — the ceiling for a hard instance>"
      }
    }
    // ... the other four spine dimensions (decomposition_milestones,
    // verification_strategy, progress_monitoring, adaptation_correction),
    // then 0-5 extra dimensions with "spine": false and a task-specific "id".
  ]
}
```

Always include exactly the five spine dimensions (never omit one — use low
importance / target_level when a task barely warrants it), plus at most five extras.

Judge only genuine process quality. Do not assume the task's outcome. Do not reward
verbosity. Do not impose meta-work the task does not warrant. Output only the JSON.
