#!/usr/bin/env python3
"""CLI script to validate reserved margin formulas against Hyperliquid API."""

import asyncio
import json
import argparse
import sys
from pathlib import Path

from src.liquidationheatmap.hyperliquid.margin_validator import MarginValidator

async def main():
    parser = argparse.ArgumentParser(description="Validate Hyperliquid MMR calculations vs API")
    parser.add_argument("--users", nargs="+", help="Specific user addresses to validate")
    parser.add_argument("--file", type=str, help="JSON file containing user addresses (e.g. outliers sample)")
    parser.add_argument("--output", type=str, default="validation_report.json", help="Output JSON report path")
    parser.add_argument("--detect-modes", action="store_true", help="Only detect margin modes for the users (skips full validation)")
    args = parser.parse_args()

    users = []
    
    if args.users:
        users.extend(args.users)
        
    if args.file:
        try:
            with open(args.file, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    extracted = [k for k in data.keys() if str(k).startswith("0x")]
                    if not extracted:
                        print(f"Warning: Could not find user addresses as top-level keys in {args.file}")
                    users.extend(extracted)
                elif isinstance(data, list):
                    extracted = [item for item in data if isinstance(item, str) and item.startswith("0x")]
                    users.extend(extracted)
        except Exception as e:
            print(f"Error reading file {args.file}: {e}")
            sys.exit(1)
            
    if not users:
        print("No users provided. Using default test set (from research.md).")
        users = [
            "0x31dea241d74ebbaedb2d71d3eb2173167b5e40e6",
            "0x57dd78225e36502da2d159a444a5d898dc2287b4",
            "0x7717a7e30dd2a9c39cc233d2a71a0af74328ce78",
            "0x7b7f722a4bbda3c0b050d268598a2eb833ddca7f",
            "0x7fdafd36f2359480a424e16d0c75cc9e909a3cf8",
            "0xab5e6f54b6ce22a868f0709b1f0cddb017f8a3d6",
            "0xd4758784bd0268ec3baee29fb3e33e9d7249826a",
            "0xecb63c20202bf74030646c2ef5f2f45cc3941459",
            "0xfc667a4e6db7365da093375f68b31a876cd64d5d"
        ]
        
    users = list(set(users))
    
    if args.detect_modes:
        print(f"Detecting modes for {len(users)} users (up to 50 max)...")
        users = users[:50]
        
        validator = MarginValidator()
        modes_count = {"cross_margin": 0, "isolated_margin": 0, "portfolio_margin": 0}
        
        for u in users:
            try:
                state = await validator.client.get_clearinghouse_state(u)
                mode = validator.detect_margin_mode(state)
                print(f"User {u}: {mode.value}")
                modes_count[mode.value] += 1
            except Exception as e:
                print(f"Failed to fetch {u}: {e}")
                
        print("\n--- Detection Summary ---")
        for mode, count in modes_count.items():
            print(f"{mode}: {count}")
        return

    print(f"Validating {len(users)} users...")
    
    validator = MarginValidator()
    report = await validator.validate_batch(users)
    
    print(f"\n--- Validation Report ---")
    print(f"Users analyzed: {report.users_analyzed}")
    print(f"Mean MMR Deviation: {report.mean_mmr_deviation_pct:.4f}%\n")
    
    for r in report.results:
        print(f"User: {r.user[:8]}... Mode: {r.mode.value}")
        print(f"  API MMR: {r.api_cross_maintenance_margin_used:.2f}  |  Sidecar MMR: {r.sidecar_total_mmr:.2f}")
        print(f"  Deviation: {r.deviation_mmr_pct:.4f}%")
        
    with open(args.output, "w") as f:
        # Convert dataclass report to dict using standard asdict or manual mapping
        import dataclasses
        json.dump(dataclasses.asdict(report), f, indent=2)
        
    print(f"\nDetailed report saved to {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
