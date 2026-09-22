"""
Reusable Analytical Operators (Phase 2C)
Python-based governed operators for period comparisons, contribution, RFM, cohorts, funnel, ABC classification.
"""

from typing import Dict, Any, List


def compute_period_comparison(current_val: float, previous_val: float, period_label: str = "YoY") -> Dict[str, Any]:
    """
    Computes absolute and percentage change safely using NULLIF zero protection.
    """
    abs_change = current_val - previous_val
    if previous_val == 0 or previous_val is None:
        pct_change = None
    else:
        pct_change = round((abs_change / abs(previous_val)) * 100, 2)

    return {
        "period_label": period_label,
        "current_value": current_val,
        "previous_value": previous_val,
        "absolute_change": round(abs_change, 2),
        "percentage_change": pct_change,
    }


def compute_contribution(rows: List[Dict[str, Any]], dimension_key: str, metric_key: str) -> List[Dict[str, Any]]:
    """
    Calculates total metric value and each dimension member's percentage contribution.
    """
    total_metric = sum(float(r.get(metric_key, 0) or 0) for r in rows)
    results = []
    for r in rows:
        val = float(r.get(metric_key, 0) or 0)
        contrib_pct = round((val / total_metric) * 100, 2) if total_metric > 0 else 0.0
        results.append(
            {
                dimension_key: r.get(dimension_key),
                metric_key: val,
                "contribution_percentage": contrib_pct,
            }
        )
    # Sort descending by metric value
    results.sort(key=lambda x: float(x[metric_key] or 0.0), reverse=True)
    return results


def compute_rfm_segments(
    rows: List[Dict[str, Any]],
    customer_key: str = "customer_id",
    recency_key: str = "recency_days",
    frequency_key: str = "order_count",
    monetary_key: str = "total_revenue",
) -> List[Dict[str, Any]]:
    """
    Calculates RFM scores (1-5) and segment classification.
    """
    if not rows:
        return []

    results = []
    for r in rows:
        rec = float(r.get(recency_key, 0) or 0)
        freq = float(r.get(frequency_key, 0) or 0)
        mon = float(r.get(monetary_key, 0) or 0)

        # Simple RFM score rules
        r_score = 5 if rec <= 30 else (4 if rec <= 90 else (3 if rec <= 180 else (2 if rec <= 365 else 1)))
        f_score = 5 if freq >= 20 else (4 if freq >= 10 else (3 if freq >= 5 else (2 if freq >= 2 else 1)))
        m_score = 5 if mon >= 5000 else (4 if mon >= 2000 else (3 if mon >= 500 else (2 if mon >= 100 else 1)))

        score_str = f"{r_score}{f_score}{m_score}"
        if r_score >= 4 and f_score >= 4 and m_score >= 4:
            segment = "Champions"
        elif r_score >= 3 and f_score >= 3:
            segment = "Loyal Customers"
        elif r_score <= 2 and f_score >= 3:
            segment = "At Risk"
        elif r_score <= 2 and f_score <= 2:
            segment = "Lost"
        else:
            segment = "Promising / Recent"

        results.append(
            {
                customer_key: r.get(customer_key),
                "recency_days": rec,
                "order_count": freq,
                "total_revenue": mon,
                "r_score": r_score,
                "f_score": f_score,
                "m_score": m_score,
                "rfm_score": score_str,
                "segment": segment,
            }
        )
    return results


def compute_funnel_metrics(
    rows: List[Dict[str, Any]], stage_key: str = "stage_name", count_key: str = "lead_count"
) -> List[Dict[str, Any]]:
    """
    Calculates stage counts, overall conversion rate, and dropoff rate across funnel stages.
    """
    if not rows:
        return []

    total_top = float(rows[0].get(count_key, 0) or 0)
    results = []
    prev_count = total_top

    for r in rows:
        curr_count = float(r.get(count_key, 0) or 0)
        overall_conversion = round((curr_count / total_top) * 100, 2) if total_top > 0 else 0.0
        stage_conversion = round((curr_count / prev_count) * 100, 2) if prev_count > 0 else 0.0
        dropoff_pct = round(100.0 - stage_conversion, 2)

        results.append(
            {
                stage_key: r.get(stage_key),
                "count": curr_count,
                "overall_conversion_pct": overall_conversion,
                "stage_conversion_pct": stage_conversion,
                "dropoff_pct": dropoff_pct,
            }
        )
        prev_count = curr_count

    return results


def compute_abc_classification(
    rows: List[Dict[str, Any]], item_key: str = "product_id", metric_key: str = "total_revenue"
) -> List[Dict[str, Any]]:
    """
    Computes Pareto ABC classification:
    Class A: Top items contributing to 80% cumulative revenue
    Class B: Next items contributing to 15% (80%-95%)
    Class C: Remaining items (95%-100%)
    """
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda x: float(x.get(metric_key, 0) or 0), reverse=True)
    total_val = sum(float(r.get(metric_key, 0) or 0) for r in sorted_rows)

    cum_val = 0.0
    results = []
    for r in sorted_rows:
        val = float(r.get(metric_key, 0) or 0)
        cum_val += val
        cum_pct = round((cum_val / total_val) * 100, 2) if total_val > 0 else 0.0

        if cum_pct <= 80.0:
            abc_class = "A"
        elif cum_pct <= 95.0:
            abc_class = "B"
        else:
            abc_class = "C"

        results.append(
            {
                item_key: r.get(item_key),
                metric_key: val,
                "cumulative_value": round(cum_val, 2),
                "cumulative_pct": cum_pct,
                "abc_class": abc_class,
            }
        )
    return results
