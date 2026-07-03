"""Meta-work judges.

- v1_fixed:    the M3 judge — one hardcoded 5-feature rubric (frozen for
               reproducibility of the M3 numbers).
- v2_adaptive: the M3.3 two-stage, task-adaptive judge — Stage A synthesizes a
               task-specific rubric from the task spec, Stage B scores a
               trajectory against it (signed-gap + profile).
"""
