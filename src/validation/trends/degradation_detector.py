"""
Degradation detection algorithm for validation metrics.

Detects model performance degradation from historical trends.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.validation.logger import logger


class DegradationSeverity(str):
    """Degradation severity levels."""

    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class DegradationDetector:
    """
    Detects model performance degradation.

    Analyzes trends to identify concerning performance drops.
    """

    def __init__(
        self,
        lookback_days: int = 30,
        minor_threshold: float = 5.0,
        moderate_threshold: float = 10.0,
        severe_threshold: float = 15.0,
        critical_threshold: float = 25.0,
    ):
        """
        Initialize degradation detector.

        Args:
            lookback_days: Days to look back for comparison
            minor_threshold: Score drop % for minor degradation
            moderate_threshold: Score drop % for moderate degradation
            severe_threshold: Score drop % for severe degradation
            critical_threshold: Score drop % for critical degradation
        """
        self.lookback_days = lookback_days
        self.minor_threshold = minor_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold
        self.critical_threshold = critical_threshold

        logger.info(
            f"DegradationDetector initialized: lookback={lookback_days}d, "
            f"thresholds=({minor_threshold}, {moderate_threshold}, "
            f"{severe_threshold}, {critical_threshold})"
        )

    def detect_score_degradation(
        self,
        scores: List[Tuple[datetime, float]],
        now_override: Optional[datetime] = None,
    ) -> Dict:
        """
        Detect degradation in overall scores.

        Args:
            scores: List of (timestamp, score) tuples

        Returns:
            Dict with degradation analysis
        """
        if len(scores) < 2:
            logger.warning("Insufficient data for degradation detection")
            return {
                "degradation_detected": False,
                "severity": DegradationSeverity.NONE,
                "message": "Insufficient data",
            }

        baseline_scores, recent_scores = self._split_by_lookback(
            scores,
            now_override=now_override,
        )

        if not baseline_scores or not recent_scores:
            logger.info("Not enough data in baseline or recent period")
            return {
                "degradation_detected": False,
                "severity": DegradationSeverity.NONE,
                "message": "Insufficient data in time windows",
            }

        # Calculate baseline and recent averages
        baseline_avg = sum(baseline_scores) / len(baseline_scores)
        recent_avg = sum(recent_scores) / len(recent_scores)

        # Calculate degradation percentage
        if baseline_avg > 0:
            degradation_pct = ((baseline_avg - recent_avg) / baseline_avg) * 100
        else:
            degradation_pct = 0

        # Determine severity
        severity = self._determine_severity(degradation_pct)

        degradation_detected = severity != DegradationSeverity.NONE

        result = {
            "degradation_detected": degradation_detected,
            "severity": severity,
            "degradation_percent": degradation_pct,
            "baseline_avg": baseline_avg,
            "recent_avg": recent_avg,
            "baseline_count": len(baseline_scores),
            "recent_count": len(recent_scores),
            "lookback_days": self.lookback_days,
        }

        if degradation_detected:
            logger.warning(
                f"Degradation detected: {severity}, {degradation_pct:.2f}% drop "
                f"(baseline={baseline_avg:.2f}, recent={recent_avg:.2f})"
            )
        else:
            logger.info(
                f"No degradation: {degradation_pct:.2f}% change "
                f"(baseline={baseline_avg:.2f}, recent={recent_avg:.2f})"
            )

        return result

    def analyze_score_trend(
        self,
        scores: List[Tuple[datetime, float]],
        now_override: Optional[datetime] = None,
    ) -> Dict:
        """Alias for testable score trend analysis."""
        return self.detect_score_degradation(scores, now_override=now_override)

    def detect_grade_degradation(
        self,
        grades: List[Tuple[datetime, str]],
        now_override: Optional[datetime] = None,
    ) -> Dict:
        """
        Detect degradation in grade distribution.

        Args:
            grades: List of (timestamp, grade) tuples

        Returns:
            Dict with grade degradation analysis
        """
        if len(grades) < 2:
            return {
                "degradation_detected": False,
                "severity": DegradationSeverity.NONE,
                "message": "Insufficient data",
            }

        baseline_grades, recent_grades = self._split_by_lookback(
            grades,
            now_override=now_override,
        )

        if not baseline_grades or not recent_grades:
            return {
                "degradation_detected": False,
                "severity": DegradationSeverity.NONE,
                "message": "Insufficient data in time windows",
            }

        # Calculate grade distributions
        baseline_dist = self._calculate_grade_distribution(baseline_grades)
        recent_dist = self._calculate_grade_distribution(recent_grades)

        # Check for degradation signals
        degradation_detected = False
        severity = DegradationSeverity.NONE

        # Signal 1: Increase in F grades
        baseline_f_pct = baseline_dist.get("F", 0) / len(baseline_grades) * 100
        recent_f_pct = recent_dist.get("F", 0) / len(recent_grades) * 100

        if recent_f_pct > baseline_f_pct + 10:  # 10% increase in F grades
            degradation_detected = True
            severity = DegradationSeverity.SEVERE

        # Signal 2: Decrease in A grades
        baseline_a_pct = baseline_dist.get("A", 0) / len(baseline_grades) * 100
        recent_a_pct = recent_dist.get("A", 0) / len(recent_grades) * 100

        if baseline_a_pct - recent_a_pct > 20:  # 20% decrease in A grades
            degradation_detected = True
            if severity == DegradationSeverity.NONE:
                severity = DegradationSeverity.MODERATE

        result = {
            "degradation_detected": degradation_detected,
            "severity": severity,
            "baseline_distribution": baseline_dist,
            "recent_distribution": recent_dist,
            "baseline_a_percent": baseline_a_pct,
            "recent_a_percent": recent_a_pct,
            "baseline_f_percent": baseline_f_pct,
            "recent_f_percent": recent_f_pct,
        }

        if degradation_detected:
            logger.warning(
                f"Grade degradation detected: {severity}, "
                f"A: {baseline_a_pct:.1f}%->{recent_a_pct:.1f}%, "
                f"F: {baseline_f_pct:.1f}%->{recent_f_pct:.1f}%"
            )

        return result

    def analyze_grade_trend(
        self,
        grades: List[Tuple[datetime, str]],
        now_override: Optional[datetime] = None,
    ) -> Dict:
        """Alias for testable grade trend analysis."""
        result = self.detect_grade_degradation(grades, now_override=now_override)
        if "baseline_f_percent" in result:
            result["baseline_f_pct"] = result["baseline_f_percent"]
        if "recent_f_percent" in result:
            result["recent_f_pct"] = result["recent_f_percent"]
        if "baseline_a_percent" in result:
            result["baseline_a_pct"] = result["baseline_a_percent"]
        if "recent_a_percent" in result:
            result["recent_a_pct"] = result["recent_a_percent"]
        return result

    def detect_test_degradation(
        self,
        test_type: str,
        test_scores: List[Tuple[datetime, float]],
    ) -> Dict:
        """
        Detect degradation in specific test performance.

        Args:
            test_type: Type of test
            test_scores: List of (timestamp, score) tuples

        Returns:
            Dict with test-specific degradation analysis
        """
        logger.info(f"Detecting degradation for {test_type}")

        result = self.detect_score_degradation(test_scores)
        result["test_type"] = test_type

        return result

    def detect_multi_metric_degradation(
        self,
        runs: List,
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """
        Detect degradation across all metrics.

        Args:
            runs: List of ValidationRun instances

        Returns:
            Dict mapping metric_name to degradation analysis
        """
        logger.info(f"Detecting multi-metric degradation for {len(runs)} runs")

        # Extract overall scores
        scores = []
        grades = []
        for run in runs:
            started_at = self._get_run_field(run, "started_at")
            overall_score = self._get_run_field(run, "overall_score")
            overall_grade = self._get_run_field(run, "overall_grade")

            if started_at is None:
                continue

            if overall_score:
                scores.append((started_at, float(overall_score)))

            if overall_grade:
                grades.append((started_at, self._normalize_grade(overall_grade)))

        degradation = {
            "overall_score": self.detect_score_degradation(scores, now_override=now_override),
            "overall_grade": self.detect_grade_degradation(grades, now_override=now_override),
        }

        # Check if any degradation detected
        any_degradation = any(d.get("degradation_detected", False) for d in degradation.values())

        degradation["summary"] = {
            "any_degradation_detected": any_degradation,
            "worst_severity": self._get_worst_severity(degradation),
        }

        logger.info(
            f"Multi-metric degradation: any={any_degradation}, "
            f"worst={degradation['summary']['worst_severity']}"
        )

        return degradation

    def analyze_multi_metric(
        self,
        run_data: List[Any],
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """Alias used by refactor-style tests and experiments."""
        result = self.detect_multi_metric_degradation(run_data, now_override=now_override)
        summary = dict(result.get("summary", {}))
        if "any_degradation_detected" in summary:
            summary["any_degradation"] = summary["any_degradation_detected"]
        result["summary"] = summary
        return result

    def _determine_severity(self, degradation_pct: float) -> str:
        """
        Determine degradation severity from percentage drop.

        Args:
            degradation_pct: Percentage degradation (positive = worse)

        Returns:
            DegradationSeverity value
        """
        if degradation_pct >= self.critical_threshold:
            return DegradationSeverity.CRITICAL
        elif degradation_pct >= self.severe_threshold:
            return DegradationSeverity.SEVERE
        elif degradation_pct >= self.moderate_threshold:
            return DegradationSeverity.MODERATE
        elif degradation_pct >= self.minor_threshold:
            return DegradationSeverity.MINOR
        else:
            return DegradationSeverity.NONE

    def _calculate_grade_distribution(self, grades: List[str]) -> Dict[str, int]:
        """Calculate grade distribution."""
        distribution = {}
        for grade in grades:
            distribution[grade] = distribution.get(grade, 0) + 1
        return distribution

    def _split_by_lookback(
        self,
        time_series: List[Tuple[datetime, Any]],
        now_override: Optional[datetime] = None,
    ) -> Tuple[List[Any], List[Any]]:
        """Split timestamped values into baseline and recent windows."""
        now = now_override or datetime.utcnow()
        cutoff_date = now - timedelta(days=self.lookback_days)
        sorted_values = sorted(time_series, key=lambda item: item[0])
        baseline = [value for ts, value in sorted_values if ts < cutoff_date]
        recent = [value for ts, value in sorted_values if ts >= cutoff_date]
        return baseline, recent

    @staticmethod
    def _get_run_field(run: Any, field_name: str) -> Any:
        """Read a field from either a model object or a dict-like run."""
        if isinstance(run, dict):
            return run.get(field_name)
        return getattr(run, field_name, None)

    @staticmethod
    def _normalize_grade(grade: Any) -> str:
        """Normalize enum-like grades to their string value."""
        return getattr(grade, "value", grade)

    def _get_worst_severity(self, degradation: Dict[str, Dict]) -> str:
        """Get worst severity from degradation results."""
        severity_order = [
            DegradationSeverity.CRITICAL,
            DegradationSeverity.SEVERE,
            DegradationSeverity.MODERATE,
            DegradationSeverity.MINOR,
            DegradationSeverity.NONE,
        ]

        for severity in severity_order:
            for metric, result in degradation.items():
                if metric == "summary":
                    continue
                if result.get("severity") == severity:
                    return severity

        return DegradationSeverity.NONE


# Global detector instance
_global_detector: Optional[DegradationDetector] = None


def get_degradation_detector() -> DegradationDetector:
    """
    Get global degradation detector instance (singleton).

    Returns:
        DegradationDetector instance
    """
    global _global_detector

    if _global_detector is None:
        _global_detector = DegradationDetector()

    return _global_detector
