"""
Domain Analytical Handlers (Phase 2C)
Specialized analytics for Customer, Product, Supplier, Inventory, and Marketing Funnel domains.
Handles missing/unpopulated data gracefully with explicit warnings or unsupported status.
"""

from typing import Dict, Any, Optional


def analyze_inventory_domain(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates inventory analytics request against available warehouse tables.
    Returns explicit ANALYSIS_NOT_SUPPORTED_BY_AVAILABLE_DATA status for unpopulated inventory stock trends.
    """
    return {
        "status": "ANALYSIS_NOT_SUPPORTED_BY_AVAILABLE_DATA",
        "message": "Inventory movement and stock turnover analysis is currently unpopulated in operational datasets.",
        "data_available": False,
    }


def analyze_variance_domain(actual_val: float, target_val: Optional[float] = None) -> Dict[str, Any]:
    """
    Evaluates variance to target/budget. If target_val is None, returns explicit status that variance-to-target is unavailable.
    """
    if target_val is None:
        return {
            "status": "TARGET_UNAVAILABLE",
            "message": "Target or budget data is not available in curated warehouse tables for variance comparison.",
            "variance": None,
        }

    abs_var = actual_val - target_val
    pct_var = round((abs_var / abs(target_val)) * 100, 2) if target_val != 0 else None
    return {
        "status": "SUCCESS",
        "actual": actual_val,
        "target": target_val,
        "absolute_variance": round(abs_var, 2),
        "percentage_variance": pct_var,
    }
