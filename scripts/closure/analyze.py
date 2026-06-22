"""Load all sweep + substrate parquets, render the three headline plots,
and print the per-cell summary + discrimination slope.

Doesn't run any model calls — purely loads parquets that run_sweep.py
and run_substrate.py wrote. Re-runnable as often as you want; cheap.

Usage:
    python scripts/closure/analyze.py [--probe verify] [--dataset omni-math]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

# headless backend for scripts (notebooks override this)
matplotlib.use("Agg")

from closure.analysis import (
    cell_summary,
    discrimination_slope,
    load_all_substrates,
    load_all_sweeps,
    plot_accuracy_by_level,
    plot_verify_by_level,
    plot_verify_vs_passrate,
)


def parse_args():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--probe",       default="verify",
                    help="filter sweeps to this probe (default: verify). "
                         "Matches the prefix in 'sweep/<probe>__...'.")
    ap.add_argument("--dataset",     default="omni-math",
                    help="filter sweeps + substrates to this dataset "
                         "(default: omni-math)")
    ap.add_argument("--results-dir", default="results",
                    help="where parquets live (default: 'results')")
    return ap.parse_args()


def main():
    args = parse_args()
    df = load_all_sweeps(args.results_dir, probe=args.probe, dataset=args.dataset)
    sub = load_all_substrates(args.results_dir, dataset=args.dataset)
    summary = cell_summary(df)
    slopes = discrimination_slope(summary)

    print(f"loaded {len(df)} sweep rows / {len(sub)} substrate rows")
    print()
    print("--- per-cell summary ---")
    print(summary.to_string(index=False))
    print()
    print("--- discrimination slope ---")
    print(slopes.to_string(index=False))

    plots_dir = Path(args.results_dir) / "plots" / args.probe / args.dataset
    print(f"\n--- saving plots to {plots_dir}/ ---")
    plot_verify_by_level(summary, plots_dir=plots_dir)
    plot_verify_vs_passrate(summary, sub, plots_dir=plots_dir)
    plot_accuracy_by_level(summary, plots_dir=plots_dir)


if __name__ == "__main__":
    main()
