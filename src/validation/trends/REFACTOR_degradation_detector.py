"""REFACTORED Degradation detection algorithm for validation metrics.

Implements structural refactoring for 100% testability:
1. Pure mathematical logic isolated from IO and system time
2. Decoupled from complex model objects (uses primitives/dicts)
3. Explicit threshold management
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from src.validation.logger import logger

class DegradationSeverity:
    """Degradation severity levels."""
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"

    @classmethod
    def get_ordered(cls) -> List[str]:
        return [cls.CRITICAL, cls.SEVERE, cls.MODERATE, cls.MINOR, cls.NONE]

class DegradationDetector:
    """Detects model performance degradation using testable pure logic."""

    def __init__(
        self,
        lookback_days: int = 30,
        minor_threshold: float = 5.0,
        moderate_threshold: float = 10.0,
        severe_threshold: float = 15.0,
        critical_threshold: float = 25.0,
    ):
        self.lookback_days = lookback_days
        self.minor_threshold = minor_threshold
        self.moderate_threshold = moderate_threshold
        self.severe_threshold = severe_threshold
        self.critical_threshold = critical_threshold

    def analyze_score_trend(
        self,
        scores: List[Tuple[datetime, float]],
        now_override: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """PURE LOGIC: Detect degradation in overall scores."""
        now = now_override or datetime.utcnow()
        
        if len(scores) < 2:
            return {"degradation_detected": False, "severity": DegradationSeverity.NONE, "message": "Insufficient data"}

        # 1. Split data into periods
        sorted_data = sorted(scores, key=lambda x: x[0])
        cutoff = now - timedelta(days=self.lookback_days)
        
        baseline = [s for ts, s in sorted_data if ts < cutoff]
        recent = [s for ts, s in sorted_data if ts >= cutoff]

        if not baseline or not recent:
            return {"degradation_detected": False, "severity": DegradationSeverity.NONE, "message": "Missing period data"}

        # 2. Calculate statistics
        b_avg = sum(baseline) / len(baseline)
        r_avg = sum(recent) / len(recent)
        
        drop_pct = 0.0
        if b_avg > 0:
            drop_pct = ((b_avg - r_avg) / b_avg) * 100

        # 3. Determine severity
        severity = self._map_drop_to_severity(drop_pct)
        
        return {
            "degradation_detected": severity != DegradationSeverity.NONE,
            "severity": severity,
            "degradation_percent": drop_pct,
            "baseline_avg": b_avg,
            "recent_avg": r_avg,
            "baseline_count": len(baseline),
            "recent_count": len(recent)
        }

    def analyze_grade_trend(
        self,
        grades: List[Tuple[datetime, str]],
        now_override: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """PURE LOGIC: Detect shifts in grade distribution (e.g. increase in Fs)."""
        now = now_override or datetime.utcnow()
        
        if len(grades) < 2:
            return {"degradation_detected": False, "severity": DegradationSeverity.NONE}

        sorted_data = sorted(grades, key=lambda x: x[0])
        cutoff = now - timedelta(days=self.lookback_days)
        
        baseline = [g for ts, g in sorted_data if ts < cutoff]
        recent = [g for ts, g in sorted_data if ts >= cutoff]

        if not baseline or not recent:
            return {"degradation_detected": False, "severity": DegradationSeverity.NONE}

        b_dist = self._get_distribution(baseline)
        r_dist = self._get_distribution(recent)

        # Detect Signals
        severity = DegradationSeverity.NONE
        
        # Signal: Increase in F grades (>10% absolute increase)
        b_f_pct = (b_dist.get("F", 0) / len(baseline)) * 100
        r_f_pct = (r_dist.get("F", 0) / len(recent)) * 100
        
        if r_f_pct > b_f_pct + 10:
            severity = DegradationSeverity.SEVERE

        # Signal: Significant decrease in A grades (>20% absolute drop)
        b_a_pct = (b_dist.get("A", 0) / len(baseline)) * 100
        r_a_pct = (r_dist.get("A", 0) / len(recent)) * 100
        
        if b_a_pct - r_a_pct > 20:
            if severity == DegradationSeverity.NONE or severity == DegradationSeverity.MINOR:
                severity = DegradationSeverity.MODERATE

        return {
            "degradation_detected": severity != DegradationSeverity.NONE,
            "severity": severity,
            "baseline_f_pct": b_f_pct,
            "recent_f_pct": r_f_pct,
            "baseline_a_pct": b_a_pct,
            "recent_a_pct": r_a_pct
        }

    def analyze_multi_metric(self, run_data: List[Dict[str, Any]], now_override: Optional[datetime] = None) -> Dict[str, Any]:
        """PURE LOGIC: Aggregate multiple degradation signals."""
        now = now_override or datetime.utcnow()
        
        scores = []
        grades = []
        for run in run_data:
            ts = run.get("started_at")
            if not ts: continue
            
            if "overall_score" in run:
                scores.append((ts, float(run["overall_score"])))
            if "overall_grade" in run:
                grades.append((ts, str(run["overall_grade"])))

        score_analysis = self.analyze_score_trend(scores, now)
        grade_analysis = self.analyze_grade_trend(grades, now)

        # Determine worst severity
        results = [score_analysis, grade_analysis]
        worst = DegradationSeverity.NONE
        
        for sev in DegradationSeverity.get_ordered():
            if any(r.get("severity") == sev for r in results):
                worst = sev
                break

        return {
            "overall_score": score_analysis,
            "overall_grade": grade_analysis,
            "summary": {
                "any_degradation": any(r.get("degradation_detected") for r in results),
                "worst_severity": worst
            }
        }

    def _map_drop_to_severity(self, drop_pct: float) -> str:
        if drop_pct >= self.critical_threshold: return DegradationSeverity.CRITICAL
        if drop_pct >= self.severe_threshold: return DegradationSeverity.SEVERE
        if drop_pct >= self.moderate_threshold: return DegradationSeverity.MODERATE
        if drop_pct >= self.minor_threshold: return DegradationSeverity.MINOR
        return DegradationSeverity.NONE

    @staticmethod
    def _get_distribution(items: List[Any]) -> Dict[Any, int]:
        dist = {}
        for item in items:
            dist[item] = dist.get(item, 0) + 1
        return dist
