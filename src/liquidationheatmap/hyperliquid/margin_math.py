"""Pure functions for margin and liquidation math."""

from typing import TYPE_CHECKING, Dict, List, Any

if TYPE_CHECKING:
    from src.liquidationheatmap.hyperliquid.sidecar import UserPosition


DEFAULT_RESERVED_MARGIN_CANDIDATE = "B"


def get_margin_tier(notional: float, tiers: List[dict]) -> dict:
    """Find the applicable margin tier for a given notional value."""
    for t in tiers:
        if notional >= t["lower_bound"]:
            return t
    return (
        tiers[-1] if tiers else {"lower_bound": 0, "mmr_rate": 0.01, "maintenance_deduction": 0}
    )


def compute_position_maintenance_margin(
    position: Any,  # UserPosition
    mark_prices: Dict[int, float],
    asset_margin_tiers: Dict[int, List[dict]],
) -> float:
    """Compute the current maintenance margin requirement for a single position."""
    mark = mark_prices.get(position.asset_idx, position.entry_px)
    notional = abs(position.size) * mark
    tiers = asset_margin_tiers.get(position.asset_idx, [])
    tier = get_margin_tier(notional, tiers)
    requirement = notional * tier["mmr_rate"] - tier["maintenance_deduction"]
    return max(0.0, requirement)

def estimate_reserved_margin(
    orders: List[Any], # List[UserOrder]
    candidate_type: str,
    mark_prices: Dict[int, float],
    asset_meta: Dict[str, Any],
    current_positions: Dict[str, float] = None,
) -> float:
    """
    Estimate reserved margin based on 4 candidates:
    A: IM per order
    B: MMR per order
    C: Net delta IM
    D: Total IM if all fill - current IM
    """
    current_positions = current_positions or {}
    total_reserve = 0.0
    
    # Pre-group orders by coin for net delta calculations
    orders_by_coin = {}
    for o in orders:
        if o.reduce_only:
            continue
        orders_by_coin.setdefault(o.coin, []).append(o)
        
    for coin, coin_orders in orders_by_coin.items():
        if coin not in asset_meta:
            continue
        
        meta = asset_meta[coin]
        idx = meta["idx"]
        max_lev = float(meta["maxLeverage"])
        if max_lev <= 0:
            continue
            
        mark = mark_prices.get(idx, 0.0)
        
        if candidate_type in ("A", "B"):
            for o in coin_orders:
                notional = o.size * mark
                if candidate_type == "A":
                    total_reserve += notional / max_lev
                elif candidate_type == "B":
                    mmr_rate = 1.0 / (2.0 * max_lev)
                    # simplified deduction = 0 for estimation, or we could look up the tier
                    total_reserve += notional * mmr_rate
        
        elif candidate_type in ("C", "D"):
            current_sz = current_positions.get(coin, 0.0)
            # Sum side sizes
            buy_sz = sum(o.size for o in coin_orders if o.side == "B")
            sell_sz = sum(o.size for o in coin_orders if o.side == "A")
            
            # evaluate both possible sides filling
            # worst case IM between all buys filling vs all sells filling
            new_sz_if_buys = current_sz + buy_sz
            new_sz_if_sells = current_sz - sell_sz
            
            im_buys = (abs(new_sz_if_buys) * mark) / max_lev
            im_sells = (abs(new_sz_if_sells) * mark) / max_lev
            
            current_im = (abs(current_sz) * mark) / max_lev
            
            worst_case_im = max(im_buys, im_sells)
            delta_im = worst_case_im - current_im
            
            if candidate_type == "C":
                total_reserve += max(0.0, delta_im)
            elif candidate_type == "D":
                total_reserve += delta_im
                
    return total_reserve
