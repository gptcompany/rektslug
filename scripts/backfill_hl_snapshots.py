#!/usr/bin/env python3
"""Bootstrap historical Hyperliquid expert snapshots from retained ABCI anchors."""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from bisect import bisect_right
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import scripts.precompute_hl_sidecar as precompute
from src.liquidationheatmap.hyperliquid.backfill import build_backfill_batch
from src.liquidationheatmap.hyperliquid.export_layout import write_backfill_batch_record
from src.liquidationheatmap.hyperliquid.producer import produce_snapshots
from src.liquidationheatmap.hyperliquid.sidecar import DEFAULT_ABCI_ROOT
from src.liquidationheatmap.hyperliquid.snapshot_schema import ALL_EXPERT_IDS

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/validation/expert_snapshots/hyperliquid")
DEFAULT_RAW_PROVIDER_ROOT = Path("data/validation/raw_provider_api")
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True)
class SnapshotJob:
    snapshot_ts: str
    anchor_path: str
    symbols: tuple[str, ...]
    output_dir: str
    raw_provider_root: str
    skip_existing: bool


def _parse_iso8601_z(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso8601_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_days(start_day: date, end_day: date):
    current = start_day
    while current <= end_day:
        yield current
        current += timedelta(days=1)


def _normalize_symbol(symbol: str) -> str:
    token = symbol.strip().upper()
    if token.endswith("USDT"):
        return token
    return f"{token}USDT"


def _coin_symbol(symbol: str) -> str:
    return _normalize_symbol(symbol).removesuffix("USDT")


def _manifest_path(output_dir: Path, symbol: str, snapshot_ts: str) -> Path:
    return output_dir / "manifests" / symbol / f"{snapshot_ts}.json"


def build_anchor_index(abci_root: Path, start_ts: datetime, end_ts: datetime) -> list[tuple[float, Path]]:
    entries: list[tuple[float, Path]] = []
    scan_start = start_ts.date() - timedelta(days=1)
    scan_end = end_ts.date()
    for day in _iter_days(scan_start, scan_end):
        day_dir = abci_root / day.strftime("%Y%m%d")
        if not day_dir.exists():
            continue
        for path in sorted(day_dir.glob("*.rmp")):
            try:
                entries.append((path.stat().st_mtime, path))
            except FileNotFoundError:
                continue
    entries.sort(key=lambda item: (item[0], str(item[1])))
    return entries


def resolve_anchor(anchor_index: list[tuple[float, Path]], snapshot_ts: datetime) -> Path | None:
    if not anchor_index:
        return None
    times = [item[0] for item in anchor_index]
    idx = bisect_right(times, snapshot_ts.timestamp()) - 1
    if idx < 0:
        return None
    return anchor_index[idx][1]


def classify_manifest_status(manifest) -> str:
    statuses = [entry.availability_status for entry in manifest.experts.values()]
    return classify_expert_statuses(statuses)


def classify_expert_statuses(statuses: list[str]) -> str:
    if any(status == "available" for status in statuses):
        return "success" if all(status == "available" for status in statuses) else "partial"
    if any(status == "failed_decode" for status in statuses):
        return "failure"
    return "gap"


def _classify_existing_manifest(output_dir: Path, symbol: str, snapshot_ts: str) -> str:
    manifest_path = _manifest_path(output_dir, symbol, snapshot_ts)
    with manifest_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    experts = payload.get("experts", {})
    if not isinstance(experts, dict):
        return "failure"

    statuses = []
    for entry in experts.values():
        if not isinstance(entry, dict):
            return "failure"
        statuses.append(str(entry.get("availability_status", "missing")))
    return classify_expert_statuses(statuses)


def _write_cache_payloads(cache_dir: Path, contexts: list[precompute.SymbolBuildContext]) -> None:
    for context in contexts:
        payload = precompute._build_public_payload(
            context=context,
            source="hyperliquid-sidecar",
            projection_mode="full_universe",
            reported_account_count=len(context.state.users),
        )
        precompute.atomic_write_json(
            payload,
            cache_dir / f"hl_sidecar_{context.symbol.lower()}usdt.json",
        )

        payload_v3 = precompute._build_v3_payload(context)
        if payload_v3 is not None:
            precompute.atomic_write_json(
                payload_v3,
                cache_dir / f"hl_sidecar_v3_{context.symbol.lower()}usdt.json",
            )

        payload_v4 = precompute._build_v4_payload(context)
        if payload_v4 is not None:
            precompute.atomic_write_json(
                payload_v4,
                cache_dir / f"hl_sidecar_v4_{context.symbol.lower()}usdt.json",
            )

        payload_v5 = precompute._build_v5_payload(context)
        if payload_v5 is not None:
            precompute.atomic_write_json(
                payload_v5,
                cache_dir / f"hl_sidecar_v5_{context.symbol.lower()}usdt.json",
            )


def _run_snapshot_job(job: SnapshotJob) -> dict:
    output_dir = Path(job.output_dir)
    existing_symbols = {
        symbol for symbol in job.symbols if job.skip_existing and _manifest_path(output_dir, symbol, job.snapshot_ts).exists()
    }
    symbols_to_process = [symbol for symbol in job.symbols if symbol not in existing_symbols]
    statuses = {
        symbol: _classify_existing_manifest(output_dir, symbol, job.snapshot_ts)
        for symbol in existing_symbols
    }
    if not symbols_to_process:
        return {
            "snapshot_ts": job.snapshot_ts,
            "anchor_path": job.anchor_path,
            "statuses": statuses,
        }

    with tempfile.TemporaryDirectory(prefix="hl-backfill-cache-") as tmp_dir:
        cache_dir = Path(tmp_dir)
        contexts = precompute.prepare_symbol_contexts(
            [_coin_symbol(symbol) for symbol in symbols_to_process],
            analysis_end=_parse_iso8601_z(job.snapshot_ts),
            anchor_path=job.anchor_path,
            enable_live_enrichment=False,
        )
        _write_cache_payloads(cache_dir, contexts)

        context_by_symbol = {f"{context.symbol}USDT": context for context in contexts}
        for symbol in symbols_to_process:
            if symbol not in context_by_symbol:
                statuses[symbol] = "gap"
                continue
            manifest = produce_snapshots(
                snapshot_ts=job.snapshot_ts,
                run_kind="backfill",
                output_dir=output_dir,
                last_actual_run_ts=job.snapshot_ts,
                cache_dir=cache_dir,
                raw_provider_root=job.raw_provider_root,
                symbol=symbol,
            )
            statuses[symbol] = classify_manifest_status(manifest)

    return {
        "snapshot_ts": job.snapshot_ts,
        "anchor_path": job.anchor_path,
        "statuses": statuses,
    }


def _aggregate_coverage(results: list[dict], symbols: tuple[str, ...]) -> dict[str, dict[str, int]]:
    coverage = {
        symbol: {"success": 0, "partial": 0, "gap": 0, "failure": 0, "skipped": 0}
        for symbol in symbols
    }
    for result in results:
        for symbol, status in result["statuses"].items():
            coverage[symbol][status] = coverage[symbol].get(status, 0) + 1
    return coverage


def _build_jobs(
    *,
    start_ts: datetime,
    end_ts: datetime,
    step_minutes: int,
    symbols: tuple[str, ...],
    output_dir: Path,
    raw_provider_root: Path,
    skip_existing: bool,
    anchor_index: list[tuple[float, Path]],
) -> tuple[list[SnapshotJob], list[dict[str, str]]]:
    jobs: list[SnapshotJob] = []
    skipped: list[dict[str, str]] = []
    current = start_ts
    while current <= end_ts:
        snapshot_ts = _format_iso8601_z(current)
        anchor = resolve_anchor(anchor_index, current)
        if anchor is None:
            skipped.append({"snapshot_ts": snapshot_ts, "reason": "no_anchor_at_or_before_snapshot"})
            current += timedelta(minutes=step_minutes)
            continue
        jobs.append(
            SnapshotJob(
                snapshot_ts=snapshot_ts,
                anchor_path=str(anchor),
                symbols=symbols,
                output_dir=str(output_dir),
                raw_provider_root=str(raw_provider_root),
                skip_existing=skip_existing,
            )
        )
        current += timedelta(minutes=step_minutes)
    return jobs, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical Hyperliquid snapshot bootstrap")
    parser.add_argument("--start-ts", required=True, help="Inclusive ISO8601 Z start")
    parser.add_argument("--end-ts", required=True, help="Inclusive ISO8601 Z end")
    parser.add_argument("--step-minutes", type=int, default=60, help="Snapshot cadence for bootstrap")
    parser.add_argument("--workers", type=int, default=2, help="Parallel anchor workers")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--raw-provider-root", default=str(DEFAULT_RAW_PROVIDER_ROOT))
    parser.add_argument("--abci-root", default=str(DEFAULT_ABCI_ROOT))
    parser.add_argument("--batch-id", help="Optional stable batch id")
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Rebuild snapshots even when manifests already exist",
    )
    return parser.parse_args()


def _build_batch_payload(
    *,
    batch_id: str,
    start_ts: datetime,
    end_ts: datetime,
    step_minutes: int,
    workers: int,
    symbols: tuple[str, ...],
    abci_root: Path,
    results: list[dict],
    skipped_without_anchor: list[dict[str, str]],
    status: str,
    started_at: datetime,
    requested_slots: int | None = None,
    error: str | None = None,
) -> dict:
    requested_slot_count = requested_slots
    if requested_slot_count is None:
        requested_slot_count = len(results) + len(skipped_without_anchor)

    batch_record = build_backfill_batch(
        batch_id=batch_id,
        interval=f"{step_minutes}m",
        symbols=list(symbols),
        experts=list(ALL_EXPERT_IDS),
        start_ts=_format_iso8601_z(start_ts),
        end_ts=_format_iso8601_z(end_ts),
        coverage=_aggregate_coverage(results, symbols),
        timeline_policy="fixed_step_latest_anchor_mtime_lte_snapshot",
        input_identity={
            "abci_root": str(abci_root),
            "requested_slots": requested_slot_count,
            "anchors_used": [
                {"snapshot_ts": result["snapshot_ts"], "anchor_path": result["anchor_path"]}
                for result in results[:100]
            ],
            "anchors_used_total": len(results),
            "anchor_resolution_failures": skipped_without_anchor[:100],
            "anchor_resolution_failures_total": len(skipped_without_anchor),
        },
    )
    payload = asdict(batch_record)
    payload["generation_metadata"] = {
        "status": status,
        "run_started_at": _format_iso8601_z(started_at),
        "generated_at": _format_iso8601_z(datetime.now(timezone.utc)),
        "workers": workers,
        "step_minutes": step_minutes,
        "results_count": len(results),
        "error": error,
    }
    if status == "completed":
        payload["generation_metadata"]["run_completed_at"] = _format_iso8601_z(
            datetime.now(timezone.utc)
        )
    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()

    start_ts = _parse_iso8601_z(args.start_ts)
    end_ts = _parse_iso8601_z(args.end_ts)
    if end_ts < start_ts:
        raise ValueError("end-ts must be >= start-ts")
    if args.step_minutes <= 0:
        raise ValueError("step-minutes must be > 0")
    if args.workers <= 0:
        raise ValueError("workers must be > 0")

    symbols = tuple(_normalize_symbol(symbol) for symbol in args.symbols)
    output_dir = Path(args.output_dir)
    raw_provider_root = Path(args.raw_provider_root)
    abci_root = Path(args.abci_root)
    started_at = datetime.now(timezone.utc)
    batch_id = args.batch_id or (
        f"backfill_hyperliquid_{start_ts.strftime('%Y%m%dT%H%M%SZ')}_{end_ts.strftime('%Y%m%dT%H%M%SZ')}_{args.step_minutes}m"
    )

    anchor_index = build_anchor_index(abci_root, start_ts, end_ts)
    jobs, skipped_without_anchor = _build_jobs(
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=args.step_minutes,
        symbols=symbols,
        output_dir=output_dir,
        raw_provider_root=raw_provider_root,
        skip_existing=not args.overwrite_existing,
        anchor_index=anchor_index,
    )
    logger.info("Prepared %d backfill jobs across %d symbols", len(jobs), len(symbols))

    results: list[dict] = []
    scheduled_results = [
        {"snapshot_ts": job.snapshot_ts, "anchor_path": job.anchor_path, "statuses": {}}
        for job in jobs
    ]
    initial_payload = _build_batch_payload(
        batch_id=batch_id,
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=args.step_minutes,
        workers=args.workers,
        symbols=symbols,
        abci_root=abci_root,
        results=scheduled_results,
        skipped_without_anchor=skipped_without_anchor,
        status="running",
        started_at=started_at,
        requested_slots=len(jobs) + len(skipped_without_anchor),
    )
    write_backfill_batch_record(output_dir, batch_id, initial_payload)

    try:
        if args.workers == 1:
            for job in jobs:
                results.append(_run_snapshot_job(job))
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(_run_snapshot_job, job) for job in jobs]
                for future in as_completed(futures):
                    results.append(future.result())
    except Exception as exc:
        results.sort(key=lambda item: item["snapshot_ts"])
        failed_payload = _build_batch_payload(
            batch_id=batch_id,
            start_ts=start_ts,
            end_ts=end_ts,
            step_minutes=args.step_minutes,
            workers=args.workers,
            symbols=symbols,
            abci_root=abci_root,
            results=results,
            skipped_without_anchor=skipped_without_anchor,
            status="failed",
            started_at=started_at,
            requested_slots=len(jobs) + len(skipped_without_anchor),
            error=str(exc),
        )
        write_backfill_batch_record(output_dir, batch_id, failed_payload)
        raise

    results.sort(key=lambda item: item["snapshot_ts"])
    payload = _build_batch_payload(
        batch_id=batch_id,
        start_ts=start_ts,
        end_ts=end_ts,
        step_minutes=args.step_minutes,
        workers=args.workers,
        symbols=symbols,
        abci_root=abci_root,
        results=results,
        skipped_without_anchor=skipped_without_anchor,
        status="completed",
        started_at=started_at,
        requested_slots=len(jobs) + len(skipped_without_anchor),
    )
    write_backfill_batch_record(output_dir, batch_id, payload)
    logger.info("Wrote backfill batch record %s", batch_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
