"""Binance Depth-Weighted liquidation model using orderbook depth."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
import pandas as pd

from .base import AbstractLiquidationModel, LiquidationLevel
from .binance_standard import BinanceStandardModel

class BinanceDepthWeightedModel(BinanceStandardModel):
    """Adjusts BinanceStandardModel liquidations using LOB depth.
    
    The probability/volume of a liquidation cluster is weighted by the 
    corresponding depth in the orderbook. Thin orderbook depth increases 
    the relative impact of a liquidation cluster.
    """

    @property
    def model_name(self) -> str:
        """Model identifier."""
        return "binance_depth_weighted"

    def calculate_liquidations(
        self,
        current_price: Decimal,
        open_interest: Decimal,
        symbol: str = "BTCUSDT",
        leverage_tiers: List[int] = None,
        num_bins: int = 50,
        large_trades=None,
        orderbook: Optional[Dict[str, Any]] = None
    ) -> List[LiquidationLevel]:
        """Calculate depth-weighted liquidations."""
        
        # Step 1: Get baseline liquidations from standard model
        baseline_levels = super().calculate_liquidations(
            current_price=current_price,
            open_interest=open_interest,
            symbol=symbol,
            leverage_tiers=leverage_tiers,
            num_bins=num_bins,
            large_trades=large_trades
        )
        
        if orderbook is None or not orderbook:
            return baseline_levels
            
        # Step 2: Weight by depth
        weighted_levels = []
        
        # Extract bid/ask depth from orderbook
        # orderbook is expected to have 'bids': [(price, qty), ...] and 'asks': [(price, qty), ...]
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        bid_df = pd.DataFrame(bids, columns=['price', 'qty'])
        ask_df = pd.DataFrame(asks, columns=['price', 'qty'])
        
        for level in baseline_levels:
            price = float(level.price_level)
            depth_available = 0.0
            
            if level.side == "long": # Liquidation price below current price (sell into bids)
                # Find bids at or above liq price
                relevant_bids = bid_df[bid_df['price'] >= price]
                depth_available = (relevant_bids['qty'] * relevant_bids['price']).sum()
            else: # Short liquidation above current price (buy from asks)
                # Find asks at or below liq price
                relevant_asks = ask_df[ask_df['price'] <= price]
                depth_available = (relevant_asks['qty'] * relevant_asks['price']).sum()
                
            # Weighting logic: thin book = higher relative impact. 
            volume = float(level.liquidation_volume)
            if depth_available > 0:
                # Impact factor increases as volume/depth_available increases
                impact_factor = 1.0 + (volume / (volume + depth_available))
            else:
                impact_factor = 2.0
                
            weighted_volume = level.liquidation_volume * Decimal(str(impact_factor))
            
            weighted_levels.append(
                LiquidationLevel(
                    timestamp=level.timestamp,
                    symbol=level.symbol,
                    price_level=level.price_level,
                    liquidation_volume=weighted_volume,
                    leverage_tier=level.leverage_tier,
                    side=level.side,
                    confidence=self.confidence_score()
                )
            )
            
        return weighted_levels

    def confidence_score(self) -> Decimal:
        """Slightly lower confidence as depth weighting is an estimate."""
        return Decimal("0.85")
