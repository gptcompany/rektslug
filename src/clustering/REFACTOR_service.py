"""REFACTORED DBSCAN clustering service for liquidation levels.

Implements structural refactoring for 100% testability:
1. De-coupled cache management (Dependency Injection)
2. Pure logic extraction for normalization and feature preparation
3. Isolated mathematical statistics from I/O
"""

import time
import logging
from typing import Dict, List, Tuple, Optional, Any, Protocol

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

from src.clustering.models import (
    ClusteringResult,
    ClusterMetadata,
    ClusterParameters,
    LiquidationCluster,
    NoisePoint,
)

logger = logging.getLogger(__name__)

class ClusteringCache(Protocol):
    """Protocol for clustering cache to allow easy mocking."""
    def get(self, key: str) -> Optional[ClusteringResult]: ...
    def set(self, key: str, value: ClusteringResult) -> None: ...
    def generate_key(self, symbol: str, timeframe: int, params: ClusterParameters) -> str: ...

class ClusteringService:
    """Service for clustering liquidation levels with testable logic."""

    def __init__(self, cache: Optional[ClusteringCache] = None):
        """Initialize with optional cache implementation."""
        self._cache = cache

    def cluster_liquidations(
        self,
        liquidations: List[Dict[str, float]],
        symbol: str,
        timeframe_minutes: int,
        params: ClusterParameters,
        use_cache: bool = True,
    ) -> ClusteringResult:
        """Coordinated clustering flow."""
        # 1. Cache Check
        if use_cache and self._cache:
            cache_key = self._cache.generate_key(symbol, timeframe_minutes, params)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        start_time = time.perf_counter()

        # 2. Empty check
        if not liquidations:
            result = self._empty_result(symbol, timeframe_minutes, params)
            return result

        # 3. Feature Prep (Pure Logic)
        features, prices = self.prepare_feature_matrix(liquidations)
        volumes = np.array([liq["volume"] for liq in liquidations])

        # 4. Clustering (Math Logic)
        epsilon = params.epsilon
        auto_tuned = False
        if params.auto_tune:
            epsilon = self.calculate_auto_epsilon(features, params.min_samples)
            auto_tuned = True

        dbscan = DBSCAN(
            eps=epsilon,
            min_samples=params.min_samples,
            metric=params.distance_metric,
        )
        labels = dbscan.fit_predict(features)

        # 5. Result Aggregation (Pure Logic)
        clusters = self.compute_cluster_stats(labels, prices, volumes)
        
        # Compute centers for noise analysis
        centers = {}
        for cluster in clusters:
            mask = labels == cluster.cluster_id
            centers[cluster.cluster_id] = np.mean(features[mask], axis=0)

        noise_points = self.compute_noise_stats(labels, prices, volumes, features, centers)

        # 6. Metadata
        comp_ms = (time.perf_counter() - start_time) * 1000
        metadata = ClusterMetadata(
            symbol=symbol,
            timeframe_minutes=timeframe_minutes,
            total_points=len(liquidations),
            cluster_count=len(clusters),
            noise_count=len(noise_points),
            parameters_used=params,
            computation_ms=comp_ms,
            auto_tuned=auto_tuned,
        )

        result = ClusteringResult(clusters=clusters, noise_points=noise_points, metadata=metadata)

        # 7. Update Cache
        if use_cache and self._cache:
            cache_key = self._cache.generate_key(symbol, timeframe_minutes, params)
            self._cache.set(cache_key, result)

        return result

    @staticmethod
    def prepare_feature_matrix(liquidations: List[Dict[str, float]]) -> Tuple[np.ndarray, np.ndarray]:
        """PURE LOGIC: Normalize price and volume into feature space."""
        prices = np.array([l["price"] for l in liquidations])
        volumes = np.array([l["volume"] for l in liquidations])
        
        log_v = np.log1p(volumes)
        
        # Normalize
        p_min, p_max = prices.min(), prices.max()
        p_norm = (prices - p_min) / (p_max - p_min) if p_max > p_min else np.zeros_like(prices)
        
        v_min, v_max = log_v.min(), log_v.max()
        v_norm = (log_v - v_min) / (v_max - v_min) if v_max > v_min else np.zeros_like(log_v)
        
        return np.column_stack([p_norm, v_norm]), prices

    @staticmethod
    def calculate_auto_epsilon(features: np.ndarray, min_samples: int) -> float:
        """PURE LOGIC: k-distance elbow heuristic."""
        if len(features) < min_samples:
            return 0.1
            
        nbrs = NearestNeighbors(n_neighbors=min_samples).fit(features)
        distances, _ = nbrs.kneighbors(features)
        k_dist = np.sort(distances[:, -1])
        
        eps = float(np.percentile(k_dist, 90))
        return round(max(0.01, min(1.0, eps)), 4)

    @staticmethod
    def compute_cluster_stats(labels: np.ndarray, prices: np.ndarray, volumes: np.ndarray) -> List[LiquidationCluster]:
        """PURE LOGIC: Aggregate raw points into cluster models."""
        clusters = []
        for cid in np.unique(labels):
            if cid == -1: continue
            
            mask = labels == cid
            c_prices = prices[mask]
            c_vols = volumes[mask]
            
            p_min, p_max = float(c_prices.min()), float(c_prices.max())
            v_total = float(c_vols.sum())
            
            centroid = float(np.average(c_prices, weights=c_vols)) if v_total > 0 else float(c_prices.mean())
            
            # Density heuristic
            spread = p_max - p_min
            density = min(1.0, len(c_prices) / (spread / 100)) if spread > 0 else 1.0
            
            clusters.append(LiquidationCluster(
                cluster_id=int(cid),
                price_min=p_min,
                price_max=p_max,
                centroid_price=centroid,
                total_volume=v_total,
                level_count=int(mask.sum()),
                density=float(density)
            ))
        return clusters

    @staticmethod
    def compute_noise_stats(
        labels: np.ndarray, 
        prices: np.ndarray, 
        volumes: np.ndarray, 
        features: np.ndarray,
        centers: Dict[int, np.ndarray]
    ) -> List[NoisePoint]:
        """PURE LOGIC: Calculate noise point metrics."""
        noise = []
        mask = labels == -1
        if not mask.any(): return []
        
        n_prices = prices[mask]
        n_vols = volumes[mask]
        n_feats = features[mask]
        
        for p, v, f in zip(n_prices, n_vols, n_feats):
            dist = 1.0
            if centers:
                dist = float(min(np.linalg.norm(f - c) for c in centers.values()))
            
            noise.append(NoisePoint(price_level=float(p), volume=float(v), distance_to_nearest=dist))
        return noise

    def _empty_result(self, symbol: str, timeframe: int, params: ClusterParameters) -> ClusteringResult:
        meta = ClusterMetadata(
            symbol=symbol, timeframe_minutes=timeframe, total_points=0,
            cluster_count=0, noise_count=0, parameters_used=params,
            computation_ms=0.0, auto_tuned=False
        )
        return ClusteringResult(clusters=[], noise_points=[], metadata=meta)
