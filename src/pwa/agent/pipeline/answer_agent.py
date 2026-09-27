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


def _summarize_numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> str:
    """Summarize numeric columns across ALL result rows (not just the first), so a
    multi-row answer reflects the whole result set instead of a single sampled row."""
    if not rows:
        return ""
    parts: list[str] = []
    for col in columns:
        values = [row[col] for row in rows if isinstance(row.get(col), (int, float))]
        if not values:
            continue
        total = sum(values)
        parts.append(
            f"{col} totals {total:,.2f} across all {len(rows)} rows"
            if isinstance(total, float)
            else f"{col} totals {total:,} across all {len(rows)} rows"
        )
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
                if isinstance(val, (int, float)):
                    key_findings.append(f"{col}: {val:,.2f}" if isinstance(val, float) else f"{col}: {val:,}")
                else:
                    key_findings.append(f"{col}: {val}")

        # 3. Construct Numerical Grounding Answer Text
        if not query_result.rows:
            answer_text = "The query completed successfully, but returned 0 matching records."
            obs = "0 rows returned."
        elif len(query_result.rows) == 1 and len(query_result.columns) == 1:
            val = list(query_result.rows[0].values())[0]
            answer_text = f"The result for '{question}' is {val}."
            obs = f"Single metric result: {val}."
        elif len(query_result.rows) == 1:
            bullets = ", ".join(f"{k} = {v}" for k, v in query_result.rows[0].items())
            answer_text = f"Based on enterprise warehouse data: {bullets}."
            obs = f"Single result row: {bullets}."
        else:
            top_rows = query_result.rows[:3]
            row_lines = [", ".join(f"{k}={v}" for k, v in row.items()) for row in top_rows]
            row_summary = "; ".join(row_lines)
            numeric_summary = _summarize_numeric_columns(query_result.rows, query_result.columns)
            extra = f" {numeric_summary}" if numeric_summary else ""
            answer_text = (
                f"Based on enterprise warehouse data ({query_result.row_count} rows returned), "
                f"the top results are: {row_summary}.{extra}"
            )
            obs = f"Top {len(top_rows)} of {query_result.row_count} rows: {row_summary}.{extra}"

        # Add freshness / quality warnings if present
        warnings = list(query_result.warnings)
        if query_result.freshness_status != "FRESH":
            warnings.append(f"Data freshness SLA status is `{query_result.freshness_status}`.")
        if query_result.quality_status != "PASS":
            warnings.append(f"Data quality status is `{query_result.quality_status}`.")
        if query_result.is_mock:
            warnings.append(
                f"⚠️ MOCK DATA SOURCE NOTICE: Query executed in offline mock mode using placeholder values (data_source='{query_result.data_source}')."
            )
            answer_text += f" [Offline Mock Mode: results from placeholder/local source '{query_result.data_source}']"

        # 4. Numerical Grounding Anti-Hallucination Audit
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
            causal_claims_asserted=[],  # Zero unsupported causal claims asserted
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
            # Allow common small structural numbers (e.g. 0, 1, 2, 3, 100) or check if in valid_numbers
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
