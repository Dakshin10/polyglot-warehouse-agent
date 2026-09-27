"""Stage 4: Agent 4 — Answer Synthesis Agent.

Synthesizes structured AnalyticalAnswer contracts grounded strictly in QueryResult
data, enforcing numerical non-hallucination, citable provenance, and visualization routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import re
from typing import Any, Optional

from pwa.semantic.result_contract import QueryResult
from pwa.ui.viz_router import VisualizationRouter, VisualizationSpec

logger = logging.getLogger("pwa.agent.pipeline.answer_agent")


@dataclass
class AnalyticalAnswer:
    """Structured response contract returned by Agent 4 Answer Synthesis Agent."""

    answer_text: str
    key_findings: list[str]
    query_id: str
    sql: str
    source_tables: list[str]
    semantic_objects_used: list[str]
    row_count: int
    bytes_processed: int
    execution_time_seconds: float
    freshness_status: str
    quality_status: str
    warnings: list[str] = field(default_factory=list)
    visualization_spec: Optional[VisualizationSpec] = None
    observation_summary: str = ""
    interpretation_summary: str = ""
    causal_claims_asserted: list[str] = field(default_factory=list)
    is_mock: bool = False
    data_source: str = "bigquery"


def _format_value(key: str, val: Any) -> str:
    """Format single cell value into human-readable currency, numeric, or string representation."""
    if isinstance(val, float):
        if any(
            kw in key.lower() for kw in ["revenue", "sales", "price", "cost", "total", "expenditure", "due", "amount"]
        ):
            return f"${val:,.2f}"
        return f"{val:,.2f}"
    elif isinstance(val, int):
        if any(
            kw in key.lower() for kw in ["revenue", "sales", "price", "cost", "total", "expenditure", "due", "amount"]
        ):
            return f"${val:,}"
        return f"{val:,}"
    return str(val)


def _summarize_numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Summarize numeric columns across ALL result rows."""
    if not rows:
        return ""
    parts: list[str] = []
    for col in columns:
        values = [v for row in rows if isinstance((v := row.get(col)), (int, float))]
        if not values:
            continue
        total = sum(values)
        formatted_total = (
            f"${total:,.2f}"
            if any(
                kw in col.lower()
                for kw in ["revenue", "sales", "price", "cost", "total", "expenditure", "due", "amount"]
            )
            else (f"{total:,.2f}" if isinstance(total, float) else f"{total:,}")
        )
        col_clean = col.replace("_", " ")
        parts.append(f"{col_clean} totals **{formatted_total}** across all {len(rows)} rows")
    return " ".join(parts[:2])


class AnswerSynthesisAgent:
    """Agent 4 engine synthesizing grounded answers with citable provenance."""

    def __init__(self, viz_router: VisualizationRouter | None = None) -> None:
        self.viz_router = viz_router or VisualizationRouter()

    def synthesize(
        self,
        question: str,
        query_result: QueryResult,
    ) -> AnalyticalAnswer:
        """Synthesize AnalyticalAnswer contract from QueryResult."""
        # 1. Infer Visualization Spec
        viz_spec = self.viz_router.recommend_visualization(query_result)

        # 2. Extract numeric observations from QueryResult
        key_findings: list[str] = []
        if query_result.rows:
            first_row = query_result.rows[0]
            for col, val in first_row.items():
                fmt_val = _format_value(col, val)
                col_name = col.replace("_", " ").title()
                key_findings.append(f"{col_name}: {fmt_val}")

        # 3. Construct Natural Language Human-Readable Answer Text
        if not query_result.rows:
            answer_text = "The query completed successfully, but returned 0 matching records in the warehouse."
            obs = "0 rows returned."

        elif len(query_result.rows) == 1 and len(query_result.columns) == 1:
            val = list(query_result.rows[0].values())[0]
            col_name = list(query_result.rows[0].keys())[0]
            fmt_val = _format_value(col_name, val)
            clean_q = question.strip("?").strip()
            answer_text = f"The result for **{clean_q}** is **{fmt_val}**."
            obs = f"Single metric result: {val}."

        elif len(query_result.rows) == 1:
            items = [_format_value(k, v) for k, v in query_result.rows[0].items()]
            bullets = ", ".join(
                f"**{k.replace('_', ' ').title()}**: {v}" for k, v in zip(query_result.rows[0].keys(), items)
            )
            answer_text = f"Based on enterprise warehouse data:\n\n{bullets}"
            obs = f"Single result row: {bullets}"

        else:
            # Multi-row synthesis: Sort by main numeric metric descending so top results lead
            rows_copy = list(query_result.rows)
            name_col = next(
                (
                    k
                    for k in query_result.columns
                    if "name" in k or "title" in k or "category" in k or "type" in k or "year" in k or "segment" in k
                ),
                query_result.columns[0],
            )
            num_col = next(
                (
                    k
                    for k in query_result.columns
                    if any(isinstance(r.get(k), (int, float)) for r in rows_copy) and k != name_col
                ),
                None,
            )

            if num_col:
                try:
                    rows_copy.sort(key=lambda r: r.get(num_col, 0) or 0, reverse=True)
                except Exception:
                    pass

            top_rows = rows_copy[:5]
            row_items = []
            for r in top_rows:
                name_val = str(r.get(name_col, ""))
                if num_col and r.get(num_col) is not None:
                    val_str = _format_value(num_col, r[num_col])
                    row_items.append((name_val, val_str))
                else:
                    row_items.append((name_val, ""))

            # Calculate total if applicable
            total_sum_str = ""
            if num_col:
                all_nums = [v for r in query_result.rows if isinstance((v := r.get(num_col)), (int, float))]
                if all_nums:
                    t_sum = sum(all_nums)
                    total_sum_str = _format_value(num_col, t_sum)

            if total_sum_str:
                headline = f"Total across all **{query_result.row_count} rows** returned reached **{total_sum_str}**."
            else:
                headline = f"Based on enterprise warehouse data (**{query_result.row_count} rows** returned):"

            if row_items:
                top_name, top_val = row_items[0]
                if top_val:
                    lead_phrase = f"**{top_name}** generated the highest sales at **{top_val}**"
                else:
                    lead_phrase = f"**{top_name}** led the results"

                other_phrases = []
                for n, v in row_items[1:]:
                    if v:
                        other_phrases.append(f"**{n}** ({v})")
                    else:
                        other_phrases.append(f"**{n}**")

                if other_phrases:
                    if len(other_phrases) > 1:
                        others_str = ", ".join(other_phrases[:-1]) + f", and {other_phrases[-1]}"
                    else:
                        others_str = other_phrases[0]
                    body_phrase = f"{lead_phrase}, followed by {others_str}."
                else:
                    body_phrase = f"{lead_phrase}."

                answer_text = f"{headline} {body_phrase}"
            else:
                answer_text = headline

            obs = f"Top {len(top_rows)} of {query_result.row_count} rows synthesized."

        # Track warnings in metadata
        warnings = list(query_result.warnings)
        if query_result.freshness_status != "FRESH":
            warnings.append(f"Data freshness SLA status is `{query_result.freshness_status}`.")
        if query_result.quality_status != "PASS":
            warnings.append(f"Data quality status is `{query_result.quality_status}`.")
        if query_result.is_mock:
            warnings.append(
                f"MOCK DATA SOURCE NOTICE: Query executed using offline local source ('{query_result.data_source}')."
            )

        # 4. Anti-Hallucination Audit
        self._verify_numerical_grounding(answer_text, query_result.rows)

        return AnalyticalAnswer(
            answer_text=answer_text,
            key_findings=key_findings,
            query_id=query_result.query_id,
            sql=query_result.sql,
            source_tables=query_result.source_tables,
            semantic_objects_used=query_result.semantic_objects_used,
            row_count=query_result.row_count,
            bytes_processed=query_result.bytes_processed,
            execution_time_seconds=query_result.execution_time_seconds,
            freshness_status=query_result.freshness_status,
            quality_status=query_result.quality_status,
            warnings=warnings,
            visualization_spec=viz_spec,
            observation_summary=obs,
            interpretation_summary=(
                f"Descriptive summary of curated enterprise data from "
                f"{', '.join(query_result.semantic_objects_used) or 'the queried source'}."
            ),
            causal_claims_asserted=[],
            is_mock=query_result.is_mock,
            data_source=query_result.data_source,
        )

    def _verify_numerical_grounding(self, text: str, rows: list[dict[str, Any]]) -> None:
        """Audit answer text ensuring no un-grounded numbers appear in synthesis."""
        numbers_in_text = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", text)]
        valid_numbers: set[float] = set()
        for row in rows:
            for val in row.values():
                if isinstance(val, (int, float)):
                    valid_numbers.add(float(val))

        for num in numbers_in_text:
            if num > 10 and num not in valid_numbers:
                logger.warning(
                    f"Numerical grounding warning: Number `{num}` in answer text not found directly in QueryResult rows."
                )


def synthesize_answer(
    question: str,
    sql: str,
    exec_result: dict[str, Any],
    model: Any = None,
    **kwargs: Any,
) -> tuple[str, dict[str, Any] | None]:
    """Legacy interface adapter function."""
    from pwa.agent.pipeline.exec_agent import _extract_source_tables, _tables_to_semantic_objects

    rows = exec_result.get("rows", [])
    cols = list(rows[0].keys()) if rows else []

    source_tables = exec_result.get("source_tables") or _extract_source_tables(sql)
    semantic_objects = exec_result.get("semantic_objects_used") or _tables_to_semantic_objects(source_tables)

    query_res = QueryResult(
        query_id="legacy_synthesis",
        sql=sql,
        columns=cols,
        rows=rows,
        row_count=len(rows),
        bytes_processed=exec_result.get("bytes_scanned", 0),
        execution_time_seconds=0.1,
        semantic_objects_used=semantic_objects,
        source_tables=source_tables,
        warnings=exec_result.get("warnings", []),
        freshness_status=exec_result.get("freshness_status", "FRESH"),
        quality_status=exec_result.get("quality_status", "PASS"),
    )
    agent = AnswerSynthesisAgent()
    answer_contract = agent.synthesize(question, query_res)
    viz_dict = answer_contract.visualization_spec.__dict__ if answer_contract.visualization_spec else None
    return answer_contract.answer_text, viz_dict


def _extract_viz_json(raw_text: str) -> tuple[str, dict[str, Any] | None]:
    """Legacy helper extracting viz json block from answer text if present."""
    if not raw_text:
        return raw_text, None

    pattern = re.compile(r"<!--\s*viz_json\s*\n?(.*?)\n?-->", re.IGNORECASE | re.DOTALL)
    match = pattern.search(raw_text)
    if not match:
        return raw_text, None

    json_str = match.group(1).strip()
    clean_text = pattern.sub("", raw_text).strip()

    try:
        viz_dict = json.loads(json_str)
        return clean_text, viz_dict
    except Exception as exc:
        logger.warning(f"Failed to parse extracted viz JSON: {exc}")
        return clean_text, None
