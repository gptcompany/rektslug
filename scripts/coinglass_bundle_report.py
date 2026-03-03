#!/usr/bin/env python3
"""Inspect the local CoinGlass frontend bundle and record hash/marker drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.compare_provider_liquidations import resolve_coinglass_bundle_path
from src.validation.constants import VALIDATION_DB_PATH

DEFAULT_DB_PATH = Path(VALIDATION_DB_PATH)
CG_TOTP_SECRET = "I65VU7K5ZQL7WB4E"
CG_AES_KEY = "1f68efd73f8d4921acc0dead41dd39bc"
CG_LOGIN_URL = "https://capi.coinglass.com/coin-community/api/user/login"
CG_LIQMAP_URL = "https://capi.coinglass.com/api/index/5/liqMap"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        help="Optional explicit bundle path. Defaults to the same bundle resolution used by the decoder.",
    )
    parser.add_argument(
        "--persist-db",
        action="store_true",
        help="Persist the observation into the validation DuckDB.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DuckDB path. Defaults to the validation DuckDB.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text.",
    )
    return parser.parse_args()


def sha256sum(path: Path) -> str:
    """Compute the SHA-256 digest for a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def isoformat_utc(timestamp: float) -> str:
    """Convert epoch seconds to an ISO UTC string."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def count_occurrences(text: str, token: str) -> int:
    """Count literal occurrences of a token in a large text blob."""
    if not token:
        return 0
    return text.count(token)


def ensure_bundle_table(conn) -> None:
    """Create bundle observation table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coinglass_bundle_observations (
            observation_id VARCHAR PRIMARY KEY,
            observed_at TIMESTAMP,
            bundle_path VARCHAR,
            sha256 VARCHAR,
            size_bytes BIGINT,
            modified_at TIMESTAMP,
            contains_totp_secret BOOLEAN,
            contains_aes_key BOOLEAN,
            contains_liqmap_endpoint BOOLEAN,
            contains_login_endpoint BOOLEAN,
            capi_occurrences INTEGER,
            liqmap_occurrences INTEGER,
            notes_json VARCHAR
        )
        """
    )


def fetch_previous_observation(conn) -> dict[str, Any] | None:
    """Return the most recent stored observation, if any."""
    cursor = conn.execute(
        """
        SELECT
            observation_id,
            observed_at,
            bundle_path,
            sha256,
            size_bytes,
            modified_at,
            contains_totp_secret,
            contains_aes_key,
            contains_liqmap_endpoint,
            contains_login_endpoint,
            capi_occurrences,
            liqmap_occurrences,
            notes_json
        FROM coinglass_bundle_observations
        ORDER BY observed_at DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, row))


def build_report(bundle_path: Path, previous: dict[str, Any] | None) -> dict[str, Any]:
    """Inspect the bundle and build a report."""
    stat = bundle_path.stat()
    text = bundle_path.read_text(encoding="utf-8", errors="ignore")
    digest = sha256sum(bundle_path)
    observed_at = datetime.now(timezone.utc).isoformat()

    markers = {
        "contains_totp_secret": CG_TOTP_SECRET in text,
        "contains_aes_key": CG_AES_KEY in text,
        "contains_liqmap_endpoint": "/api/index/5/liqMap" in text or CG_LIQMAP_URL in text,
        "contains_login_endpoint": "coin-community/api/user/login" in text or CG_LOGIN_URL in text,
        "capi_occurrences": count_occurrences(text, "capi.coinglass.com"),
        "liqmap_occurrences": count_occurrences(text, "liqMap"),
    }

    notes: list[str] = []
    if markers["contains_totp_secret"] and markers["contains_aes_key"]:
        notes.append("Current hardcoded TOTP/AES constants are still present in the bundle.")
    else:
        notes.append("One or both TOTP/AES constants were not found verbatim in the bundle.")

    if previous is None:
        notes.append("No previous bundle observation exists in DuckDB yet.")
    else:
        previous_hash = previous.get("sha256")
        if previous_hash == digest:
            notes.append("Bundle SHA-256 is unchanged from the last stored observation.")
        else:
            notes.append("Bundle SHA-256 changed since the last stored observation.")

    return {
        "observed_at": observed_at,
        "bundle_path": str(bundle_path),
        "sha256": digest,
        "size_bytes": stat.st_size,
        "modified_at": isoformat_utc(stat.st_mtime),
        "markers": markers,
        "previous_observation": previous,
        "notes": notes,
    }


def persist_report(report: dict[str, Any], db_path: Path) -> None:
    """Persist one bundle observation into the validation DuckDB."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("duckdb is required for --persist-db") from exc

    db_path.parent.mkdir(parents=True, exist_ok=True)
    observation_id = f"{report['observed_at'].replace(':', '').replace('-', '')}_coinglass_bundle"

    conn = duckdb.connect(str(db_path))
    try:
        ensure_bundle_table(conn)
        markers = report["markers"]
        conn.execute(
            """
            INSERT OR REPLACE INTO coinglass_bundle_observations
            (
                observation_id, observed_at, bundle_path, sha256, size_bytes, modified_at,
                contains_totp_secret, contains_aes_key, contains_liqmap_endpoint,
                contains_login_endpoint, capi_occurrences, liqmap_occurrences, notes_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                observation_id,
                report["observed_at"],
                report["bundle_path"],
                report["sha256"],
                report["size_bytes"],
                report["modified_at"],
                markers["contains_totp_secret"],
                markers["contains_aes_key"],
                markers["contains_liqmap_endpoint"],
                markers["contains_login_endpoint"],
                markers["capi_occurrences"],
                markers["liqmap_occurrences"],
                json.dumps(report.get("notes", []), ensure_ascii=True),
            ],
        )
    finally:
        conn.close()


def render_text(report: dict[str, Any]) -> str:
    """Render a concise text report."""
    markers = report["markers"]
    lines = [
        f"bundle: {report['bundle_path']}",
        f"sha256: {report['sha256']}",
        f"size_bytes: {report['size_bytes']}",
        f"modified_at: {report['modified_at']}",
        "",
        "Markers",
        f"- contains_totp_secret={markers['contains_totp_secret']}",
        f"- contains_aes_key={markers['contains_aes_key']}",
        f"- contains_liqmap_endpoint={markers['contains_liqmap_endpoint']}",
        f"- contains_login_endpoint={markers['contains_login_endpoint']}",
        f"- capi_occurrences={markers['capi_occurrences']}",
        f"- liqmap_occurrences={markers['liqmap_occurrences']}",
    ]
    if report.get("notes"):
        lines.append("")
        lines.append("Notes")
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    bundle_path = args.bundle or resolve_coinglass_bundle_path()
    if bundle_path is None or not bundle_path.exists():
        print("error: No local Coinglass bundle found. Set COINGLASS_APP_BUNDLE or keep _app-*.js in /tmp.")
        return 1

    previous = None
    if args.persist_db or args.db_path.exists():
        try:
            import duckdb
        except ImportError:
            duckdb = None  # type: ignore[assignment]
        if duckdb is not None and args.db_path.exists():
            try:
                conn = duckdb.connect(str(args.db_path), read_only=True)
            except Exception:
                conn = None
            if conn is not None:
                try:
                    try:
                        previous = fetch_previous_observation(conn)
                    except Exception:
                        previous = None
                finally:
                    conn.close()

    report = build_report(bundle_path, previous)

    if args.persist_db:
        persist_report(report, args.db_path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True, default=str))
    else:
        print(render_text(report))
        if args.persist_db:
            print("")
            print(f"duckdb: {args.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
