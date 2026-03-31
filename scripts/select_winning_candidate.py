#!/usr/bin/env python3
"""Select the best reserved-margin candidate from comparison artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_result(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "candidate": data["candidate"],
        "positions_compared": data["positions_compared"],
        "improved_positions": data["improved_positions"],
        "worsened_positions": data["worsened_positions"],
        "improvement_rate": data["improvement_rate"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank reserved-margin candidates from solver comparison artifacts."
    )
    parser.add_argument(
        "artifacts",
        nargs="*",
        help="Comparison artifact JSON files. Defaults to all solver_v1_vs_v1.1_comparison*.json files.",
    )
    args = parser.parse_args()

    paths = [Path(path) for path in args.artifacts] if args.artifacts else sorted(
        Path("data/validation").glob("solver_v1_vs_v1.1_comparison*.json")
    )
    if not paths:
        raise SystemExit("No comparison artifacts found.")

    results = [_load_result(path) for path in paths]
    ranked = sorted(
        results,
        key=lambda item: (
            item["improvement_rate"],
            item["improved_positions"],
            -item["worsened_positions"],
        ),
        reverse=True,
    )

    print("Reserved-margin candidate ranking:")
    for item in ranked:
        print(
            f"  {item['candidate']}: "
            f"improvement_rate={item['improvement_rate']:.4f}, "
            f"improved={item['improved_positions']}, "
            f"worsened={item['worsened_positions']}, "
            f"positions={item['positions_compared']}"
        )

    winner = ranked[0]
    print(
        f"\nWinner: Candidate {winner['candidate']} "
        f"({winner['improvement_rate']:.4f} improvement rate)"
    )


if __name__ == "__main__":
    main()
