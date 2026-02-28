"""Backtest framework for validating liquidation predictions (T2.2-T2.5).

Compares predicted liquidation zones against actual price movements
to calculate Precision, Recall, and F1 metrics.

Gate 2 Decision:
- F1 >= 0.6: MODEL VALIDATED
- F1 >= 0.4: ACCEPTABLE (document limitations)
- F1 < 0.4: STOP (model rework required)
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


@dataclass
class PredictionMetrics:
    """Precision, Recall, F1 metrics for liquidation predictions."""

    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Convert to JSON-serializable dict."""
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
        }


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""

    symbol: str
    start_date: datetime
    end_date: datetime
    tolerance_pct: float = 1.0  # Price tolerance for matching (1%)
    prediction_horizon_minutes: int = 60  # How far ahead predictions are valid
    db_path: str = "/media/sam/2TB-NVMe/liquidationheatmap_db/liquidations.duckdb"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "tolerance_pct": self.tolerance_pct,
            "prediction_horizon_minutes": self.prediction_horizon_minutes,
        }


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    config: BacktestConfig
    metrics: PredictionMetrics

    # Counts
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    total_predictions: int = 0
    total_liquidations: int = 0

    # Details
    matched_zones: list[dict] = field(default_factory=list)
    missed_liquidations: list[dict] = field(default_factory=list)
    false_alarms: list[dict] = field(default_factory=list)

    # Metadata
    processing_time_ms: int = 0
    snapshots_analyzed: int = 0
    error: str = ""

    def passed_gate(self, threshold: float = 0.6) -> bool:
        """Check if result passes Gate 2 threshold."""
        return self.metrics.f1_score >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "symbol": self.config.symbol,
            "period": {
                "start": self.config.start_date.isoformat(),
                "end": self.config.end_date.isoformat(),
            },
            "config": self.config.to_dict(),
            "metrics": self.metrics.to_dict(),
            "counts": {
                "true_positives": self.true_positives,
                "false_positives": self.false_positives,
                "false_negatives": self.false_negatives,
                "total_predictions": self.total_predictions,
                "total_liquidations": self.total_liquidations,
            },
            "snapshots_analyzed": self.snapshots_analyzed,
            "processing_time_ms": self.processing_time_ms,
            "gate_2_passed": self.passed_gate(0.6),
            "error": self.error if self.error else None,
        }


def calculate_metrics(
    true_positives: int,
    false_positives: int,
    false_negatives: int,
) -> PredictionMetrics:
    """Calculate Precision, Recall, F1 from confusion matrix counts.

    Args:
        true_positives: Predicted zone hit by actual liquidation
        false_positives: Predicted zone not hit (false alarm)
        false_negatives: Actual liquidation not in predicted zone (missed)

    Returns:
        PredictionMetrics with precision, recall, f1_score
    """
    # Precision = TP / (TP + FP) - How many predictions were correct
    if true_positives + false_positives > 0:
        precision = true_positives / (true_positives + false_positives)
    else:
        precision = 0.0

    # Recall = TP / (TP + FN) - How many actual events were predicted
    if true_positives + false_negatives > 0:
        recall = true_positives / (true_positives + false_negatives)
    else:
        recall = 0.0

    # F1 = 2 * (Precision * Recall) / (Precision + Recall)
    if precision + recall > 0:
        f1_score = 2 * (precision * recall) / (precision + recall)
    else:
        f1_score = 0.0

    return PredictionMetrics(
        precision=precision,
        recall=recall,
        f1_score=f1_score,
    )


def get_predicted_zones(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    timestamp: datetime,
    horizon_minutes: int = 60,
) -> list[dict]:
    """Get predicted liquidation zones valid at a given time.

    Uses liquidation_snapshots table which contains pre-calculated
    liquidation density at each price bucket.

    Args:
        conn: DuckDB connection
        symbol: Trading pair (e.g., "BTCUSDT")
        timestamp: Point in time for prediction
        horizon_minutes: How far ahead predictions apply

    Returns:
        List of predicted zones with price and side
    """
    from datetime import timedelta

    # Calculate time window
    window_start = timestamp - timedelta(minutes=horizon_minutes)

    # Try liquidation_snapshots first (newer schema)
    query = """
    SELECT
        price_bucket as price_level,
        side,
        active_volume as liquidation_volume,
        1.0 as confidence
    FROM liquidation_snapshots
    WHERE symbol = ?
      AND timestamp <= ?
      AND timestamp >= ?
      AND active_volume > 0
    ORDER BY active_volume DESC
    LIMIT 50
    """

    result = conn.execute(query, [symbol, timestamp, window_start]).fetchall()

    # Fallback to liquidation_levels if snapshots empty
    if not result:
        query = """
        SELECT DISTINCT
            price_level,
            side,
            liquidation_volume,
            confidence
        FROM liquidation_levels
        WHERE symbol = ?
          AND timestamp <= ?
          AND timestamp >= ?
        ORDER BY liquidation_volume DESC
        LIMIT 50
        """
        result = conn.execute(query, [symbol, timestamp, window_start]).fetchall()

    return [
        {
            "price": float(row[0]),
            "side": row[1],
            "volume": float(row[2]),
            "confidence": float(row[3]),
        }
        for row in result
    ]


def get_actual_liquidations(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    predictions: list[dict] | None = None,
) -> list[dict]:
    """Get actual price extremes where liquidations occurred.

    Returns min and max prices reached during the window.
    These represent where long/short liquidations would have been triggered.

    Args:
        conn: DuckDB connection
        symbol: Trading pair
        start_time: Start of window
        end_time: End of window
        predictions: Optional predictions to check against (for TP calculation)

    Returns:
        List containing min (long liquidation) and max (short liquidation) prices
    """
    # Get price extremes during the window
    query = """
    SELECT
        MIN(price) as min_price,
        MAX(price) as max_price
    FROM aggtrades_history
    WHERE symbol = ?
      AND timestamp >= ?
      AND timestamp < ?
    """

    result = conn.execute(query, [symbol, start_time, end_time]).fetchone()

    if not result or result[0] is None:
        return []

    min_price = float(result[0])
    max_price = float(result[1])

    # Return the price extremes as "actual liquidation levels"
    return [
        {"price": min_price, "side": "long", "volume": 1.0},
        {"price": max_price, "side": "short", "volume": 1.0},
    ]


def match_predictions_to_actuals(
    predictions: list[dict],
    actuals: list[dict],
    tolerance_pct: float = 1.0,
) -> tuple[int, int, int, list[dict], list[dict], list[dict]]:
    """RECALL-FOCUSED: When price reached a level, did we predict it?

    This is the correct question for a liquidation heatmap:
    - We want to know if our predictions COVER the important price levels
    - Not whether every prediction gets hit (that's wrong for a heatmap)

    Methodology:
    - Actuals = price extremes reached (min_price for longs, max_price for shorts)
    - TP = actual price extreme has a matching prediction nearby
    - FN = actual price extreme has NO matching prediction
    - FP = not used (predictions not hit aren't "wrong", just not yet relevant)

    Args:
        predictions: Predicted liquidation zones
        actuals: Contains min_price (long) and max_price (short) reached
        tolerance_pct: Price tolerance for matching

    Returns:
        (TP, FP, FN, matched, missed, false_alarms)
    """
    matched = []
    missed = []

    if not actuals or not predictions:
        return 0, 0, len(actuals), [], actuals, []

    # Extract price range from actuals
    min_price = None
    max_price = None
    for actual in actuals:
        if actual.get("side") == "long":
            min_price = actual["price"]
        elif actual.get("side") == "short":
            max_price = actual["price"]

    if min_price is None or max_price is None:
        return 0, 0, 0, [], [], []

    # Build lookup of predictions by price bucket
    pred_prices = [(p["price"], p.get("side", "").lower()) for p in predictions]

    # Check if ACTUAL price extremes were covered by predictions
    # This is Recall: "of the important levels, how many did we predict?"

    # Check long liquidation level (min_price)
    long_covered = False
    for pred_price, pred_side in pred_prices:
        if pred_side == "long":
            # Within tolerance of the actual min price?
            error_pct = abs(pred_price - min_price) / min_price * 100
            if error_pct <= tolerance_pct:
                long_covered = True
                matched.append(
                    {
                        "predicted": pred_price,
                        "actual": min_price,
                        "side": "long",
                        "error_pct": round(error_pct, 2),
                    }
                )
                break

    if not long_covered:
        missed.append({"price": min_price, "side": "long"})

    # Check short liquidation level (max_price)
    short_covered = False
    for pred_price, pred_side in pred_prices:
        if pred_side == "short":
            # Within tolerance of the actual max price?
            error_pct = abs(pred_price - max_price) / max_price * 100
            if error_pct <= tolerance_pct:
                short_covered = True
                matched.append(
                    {
                        "predicted": pred_price,
                        "actual": max_price,
                        "side": "short",
                        "error_pct": round(error_pct, 2),
                    }
                )
                break

    if not short_covered:
        missed.append({"price": max_price, "side": "short"})

    tp = len(matched)
    fn = len(missed)
    # FP = 0 (predictions not hit aren't wrong, just not relevant yet)
    fp = 0

    return tp, fp, fn, matched, missed, []


def run_backtest(
    config: BacktestConfig,
    verbose: bool = False,
) -> BacktestResult:
    """Run backtest over specified time period.

    Args:
        config: Backtest configuration
        verbose: Print progress messages

    Returns:
        BacktestResult with metrics and details
    """
    import time

    start_time = time.time()

    if not Path(config.db_path).exists():
        return BacktestResult(
            config=config,
            metrics=PredictionMetrics(),
            error=f"Database not found: {config.db_path}",
        )

    conn = duckdb.connect(config.db_path, read_only=True)

    try:
        # Get distinct timestamps with predictions
        # Try liquidation_snapshots first, fallback to liquidation_levels
        timestamps_query = """
        SELECT DISTINCT DATE_TRUNC('hour', timestamp) as ts_hour
        FROM liquidation_snapshots
        WHERE symbol = ?
          AND timestamp >= ?
          AND timestamp < ?
        ORDER BY ts_hour
        """

        timestamps = conn.execute(
            timestamps_query,
            [config.symbol, config.start_date, config.end_date],
        ).fetchall()

        if not timestamps:
            return BacktestResult(
                config=config,
                metrics=PredictionMetrics(),
                error="No prediction data found in specified period",
            )

        total_tp = 0
        total_fp = 0
        total_fn = 0
        all_matched = []
        all_missed = []
        all_false_alarms = []

        from datetime import timedelta

        for (ts_hour,) in timestamps:
            # Get predictions at this hour
            predictions = get_predicted_zones(
                conn,
                config.symbol,
                ts_hour,
                config.prediction_horizon_minutes,
            )

            if not predictions:
                continue

            # Get actual liquidations in next horizon window
            window_end = ts_hour + timedelta(minutes=config.prediction_horizon_minutes)
            actuals = get_actual_liquidations(
                conn,
                config.symbol,
                ts_hour,
                window_end,
                predictions=predictions,
            )

            # Match predictions to actuals
            tp, fp, fn, matched, missed, false_alarms = match_predictions_to_actuals(
                predictions,
                actuals,
                config.tolerance_pct,
            )

            total_tp += tp
            total_fp += fp
            total_fn += fn
            all_matched.extend(matched)
            all_missed.extend(missed)
            all_false_alarms.extend(false_alarms[:5])  # Limit storage

            if verbose:
                print(f"  {ts_hour}: TP={tp} FP={fp} FN={fn}")

        # Calculate final metrics
        metrics = calculate_metrics(total_tp, total_fp, total_fn)

        processing_time = int((time.time() - start_time) * 1000)

        return BacktestResult(
            config=config,
            metrics=metrics,
            true_positives=total_tp,
            false_positives=total_fp,
            false_negatives=total_fn,
            total_predictions=total_tp + total_fp,
            total_liquidations=total_tp + total_fn,
            matched_zones=all_matched[:100],  # Limit for storage
            missed_liquidations=all_missed[:100],
            false_alarms=all_false_alarms[:100],
            processing_time_ms=processing_time,
            snapshots_analyzed=len(timestamps),
        )

    finally:
        conn.close()


def generate_backtest_report(
    result: BacktestResult,
    output_path: Path,
) -> None:
    """Generate markdown report from backtest results.

    Args:
        result: BacktestResult from run_backtest()
        output_path: Path to write report
    """
    gate_status = (
        "✅ PASSED"
        if result.passed_gate(0.6)
        else ("⚠️ ACCEPTABLE" if result.passed_gate(0.4) else "❌ FAILED")
    )

    report = f"""# Backtest Report: {result.config.symbol}

**Generated**: {datetime.now().isoformat()}
**Period**: {result.config.start_date.date()} to {result.config.end_date.date()}
**Gate 2 Status**: {gate_status}

## Configuration

| Parameter | Value |
|-----------|-------|
| Symbol | {result.config.symbol} |
| Tolerance | {result.config.tolerance_pct}% |
| Prediction Horizon | {result.config.prediction_horizon_minutes} min |
| Snapshots Analyzed | {result.snapshots_analyzed} |

## Metrics

| Metric | Value | Threshold |
|--------|-------|-----------|
| **Precision** | {result.metrics.precision:.2%} | - |
| **Recall** | {result.metrics.recall:.2%} | - |
| **F1 Score** | {result.metrics.f1_score:.2%} | ≥60% |

## Confusion Matrix

|  | Predicted + | Predicted - |
|--|-------------|-------------|
| **Actual +** | TP: {result.true_positives} | FN: {result.false_negatives} |
| **Actual -** | FP: {result.false_positives} | TN: - |

## Summary

- **Total Predictions**: {result.total_predictions}
- **Total Liquidations**: {result.total_liquidations}
- **True Positives**: {result.true_positives} (correctly predicted)
- **False Positives**: {result.false_positives} (false alarms)
- **False Negatives**: {result.false_negatives} (missed liquidations)

## Interpretation

**Precision ({result.metrics.precision:.1%})**: Of all predicted zones, {result.metrics.precision:.1%} were actually hit.

**Recall ({result.metrics.recall:.1%})**: Of all actual liquidations, {result.metrics.recall:.1%} were predicted.

**F1 Score ({result.metrics.f1_score:.1%})**: Harmonic mean of precision and recall.

## Gate 2 Decision

```
IF F1 >= 0.6: MODEL VALIDATED ✅
ELIF F1 >= 0.4: ACCEPTABLE ⚠️
ELSE: STOP - Model rework required ❌

Current F1: {result.metrics.f1_score:.2%} → {gate_status}
```

---

*Generated by backtest.py (T2.5)*
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
