"""Unit tests for REFACTORED clustering service."""

import pytest
import numpy as np
from unittest.mock import MagicMock
from src.clustering.REFACTOR_service import ClusteringService, ClusteringCache
from src.clustering.models import ClusterParameters

class TestREFACTORClusteringService:
    def test_prepare_feature_matrix(self):
        """Should normalize prices and volumes."""
        liquidations = [
            {"price": 40000.0, "volume": 100.0},
            {"price": 50000.0, "volume": 1000.0},
        ]
        features, prices = ClusteringService.prepare_feature_matrix(liquidations)
        
        assert features.shape == (2, 2)
        assert prices[0] == 40000.0
        # Check normalization bounds
        assert np.all(features >= 0.0)
        assert np.all(features <= 1.0)

    def test_cluster_liquidations_two_groups(self):
        """Should identify two distinct clusters."""
        # Group 1 around 40k, Group 2 around 60k
        data = []
        for p in [39900, 40000, 40100]:
            data.append({"price": float(p), "volume": 100.0})
        for p in [59900, 60000, 60100]:
            data.append({"price": float(p), "volume": 100.0})
            
        params = ClusterParameters(epsilon=0.2, min_samples=2)
        service = ClusteringService()
        result = service.cluster_liquidations(data, "BTCUSDT", 60, params, use_cache=False)
        
        assert result.metadata.cluster_count == 2
        assert len(result.clusters) == 2
        assert result.metadata.total_points == 6

    def test_noise_detection(self):
        """Should identify isolated points as noise."""
        data = [
            {"price": 40000.0, "volume": 100.0},
            {"price": 40010.0, "volume": 100.0},
            {"price": 90000.0, "volume": 1.0}, # Noise
        ]
        params = ClusterParameters(epsilon=0.05, min_samples=2)
        service = ClusteringService()
        result = service.cluster_liquidations(data, "BTCUSDT", 60, params, use_cache=False)
        
        assert result.metadata.cluster_count == 1
        assert result.metadata.noise_count == 1
        assert result.noise_points[0].price_level == 90000.0

    def test_cache_interaction(self):
        """Should check cache before computing and set cache after."""
        mock_cache = MagicMock(spec=ClusteringCache)
        mock_cache.generate_key.return_value = "key123"
        mock_cache.get.return_value = None # Cache miss
        
        data = [{"price": 40000.0, "volume": 100.0}, {"price": 40001.0, "volume": 100.0}]
        params = ClusterParameters()
        service = ClusteringService(cache=mock_cache)
        
        service.cluster_liquidations(data, "BTCUSDT", 60, params)
        
        assert mock_cache.get.called
        assert mock_cache.set.called

    def test_auto_epsilon_logic(self):
        """Should compute a valid epsilon via auto-tune."""
        data = []
        for i in range(10):
            data.append({"price": 40000.0 + i*10, "volume": 100.0})
            
        params = ClusterParameters(auto_tune=True, min_samples=3)
        service = ClusteringService()
        result = service.cluster_liquidations(data, "BTCUSDT", 60, params, use_cache=False)
        
        assert result.metadata.auto_tuned is True
        assert 0.01 <= result.metadata.parameters_used.epsilon <= 1.0
