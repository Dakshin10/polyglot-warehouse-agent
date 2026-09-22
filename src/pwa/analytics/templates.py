"""
Pre-packaged Analytical Templates (Phase 2C)
Defines multi-step deterministic workflow templates for diagnostic, cohort, funnel, and contribution analysis.
"""

from typing import Dict, Any, Optional
from pwa.analytics.models import AnalyticalWorkflow, WorkflowStep, StepOperation, AnalyticalOperator


def get_workflow_template(template_name: str, params: Optional[Dict[str, Any]] = None) -> Optional[AnalyticalWorkflow]:
    params = params or {}

    if template_name in ("revenue_decline_analysis", "diagnostic_analysis"):
        return AnalyticalWorkflow(
            workflow_id="wf_revenue_decline_diagnostic",
            name="Revenue Decline Diagnostic Workflow",
            description="Decomposes revenue changes across volume (order_count), price/mix (average_order_value), and category contribution.",
            inputs={"metric": "revenue", "time_dimension": "order_date"},
            steps=[
                WorkflowStep(
                    step_id="step_1_time_series",
                    description="Calculate monthly revenue time series",
                    operation=StepOperation(
                        operator=AnalyticalOperator.TIME_SERIES,
                        params={"metric": "revenue", "granularity": "month"},
                    ),
                    semantic_objects={"entity": "fact_sales_order", "measure": "revenue"},
                ),
                WorkflowStep(
                    step_id="step_2_order_count",
                    description="Calculate monthly order count time series",
                    operation=StepOperation(
                        operator=AnalyticalOperator.TIME_SERIES,
                        params={"metric": "order_count", "granularity": "month"},
                    ),
                    semantic_objects={"entity": "fact_sales_order", "measure": "order_count"},
                ),
                WorkflowStep(
                    step_id="step_3_aov",
                    description="Calculate monthly average order value (AOV)",
                    operation=StepOperation(
                        operator=AnalyticalOperator.TIME_SERIES,
                        params={"metric": "average_order_value", "granularity": "month"},
                    ),
                    semantic_objects={"entity": "fact_sales_order", "metric": "average_order_value"},
                ),
                WorkflowStep(
                    step_id="step_4_period_comp",
                    description="Compare current vs previous period",
                    operation=StepOperation(
                        operator=AnalyticalOperator.PERIOD_COMPARISON,
                        params={"period_label": "MoM"},
                    ),
                    input_step_ids=["step_1_time_series"],
                ),
                WorkflowStep(
                    step_id="step_5_category_contrib",
                    description="Identify top category contributors to revenue change",
                    operation=StepOperation(
                        operator=AnalyticalOperator.CONTRIBUTION,
                        params={"dimension": "product_category", "metric": "revenue"},
                    ),
                    semantic_objects={"entity": "dim_product", "dimension": "product_category"},
                ),
            ],
            outputs=["revenue_trend", "order_count_trend", "aov_trend", "period_comparison", "category_contribution"],
        )

    elif template_name in ("period_comparison", "yoy_analysis", "mom_analysis"):
        return AnalyticalWorkflow(
            workflow_id="wf_period_comparison",
            name="Period-Over-Period Comparison Workflow",
            description="Computes YoY/MoM metric change with safe NULLIF zero division protection.",
            inputs={"metric": params.get("metric", "revenue")},
            steps=[
                WorkflowStep(
                    step_id="step_1_time_series",
                    description="Extract metric time series",
                    operation=StepOperation(
                        operator=AnalyticalOperator.TIME_SERIES,
                        params={"metric": params.get("metric", "revenue"), "granularity": "month"},
                    ),
                ),
                WorkflowStep(
                    step_id="step_2_period_comp",
                    description="Compute period comparison",
                    operation=StepOperation(
                        operator=AnalyticalOperator.PERIOD_COMPARISON,
                        params={"period_label": params.get("period_label", "YoY")},
                    ),
                    input_step_ids=["step_1_time_series"],
                ),
            ],
            outputs=["time_series", "period_comparison"],
        )

    elif template_name in ("customer_cohort_analysis", "cohort_analysis"):
        return AnalyticalWorkflow(
            workflow_id="wf_customer_cohort",
            name="Customer Cohort & Retention Workflow",
            description="Analyzes customer acquisition month cohorts and subsequent order repeat rates.",
            inputs={"entity": "dim_customer"},
            steps=[
                WorkflowStep(
                    step_id="step_1_cohort_matrix",
                    description="Generate customer acquisition cohort matrix",
                    operation=StepOperation(
                        operator=AnalyticalOperator.COHORT,
                        params={"cohort_grain": "first_purchase_month"},
                    ),
                    semantic_objects={"entity": "dim_customer"},
                ),
                WorkflowStep(
                    step_id="step_2_retention_curve",
                    description="Calculate period retention rates across cohorts",
                    operation=StepOperation(
                        operator=AnalyticalOperator.RETENTION,
                        params={"periods": [0, 1, 2, 3, 6, 12]},
                    ),
                    input_step_ids=["step_1_cohort_matrix"],
                ),
            ],
            outputs=["cohort_matrix", "retention_curve"],
        )

    elif template_name in ("marketing_funnel_analysis", "funnel_analysis"):
        return AnalyticalWorkflow(
            workflow_id="wf_marketing_funnel",
            name="Marketing Funnel & Conversion Workflow",
            description="Tracks lead progression from Lead -> Qualified -> Closed with conversion and dropoff rates.",
            inputs={"entity": "dim_lead"},
            steps=[
                WorkflowStep(
                    step_id="step_1_funnel_stages",
                    description="Aggregate lead counts by funnel stage",
                    operation=StepOperation(
                        operator=AnalyticalOperator.FUNNEL,
                        params={"stages": ["Lead", "Qualified", "Closed"]},
                    ),
                    semantic_objects={"entity": "dim_lead", "measure": "lead_count"},
                ),
            ],
            outputs=["funnel_stages"],
        )

    elif template_name in ("product_mix_analysis", "abc_classification"):
        return AnalyticalWorkflow(
            workflow_id="wf_product_mix_abc",
            name="Product Mix & Pareto ABC Classification Workflow",
            description="Classifies products into A (top 80%), B (next 15%), and C (remaining 5%) categories.",
            inputs={"entity": "dim_product"},
            steps=[
                WorkflowStep(
                    step_id="step_1_product_revenue",
                    description="Aggregate revenue by product",
                    operation=StepOperation(
                        operator=AnalyticalOperator.GROUP_BY,
                        params={"dimension": "product_name", "metric": "revenue"},
                    ),
                    semantic_objects={"entity": "dim_product", "measure": "revenue"},
                ),
                WorkflowStep(
                    step_id="step_2_abc_class",
                    description="Compute Pareto ABC classification",
                    operation=StepOperation(
                        operator=AnalyticalOperator.RANK,
                        params={"metric": "revenue", "method": "abc_classification"},
                    ),
                    input_step_ids=["step_1_product_revenue"],
                ),
            ],
            outputs=["product_revenue", "abc_classification"],
        )

    return None
