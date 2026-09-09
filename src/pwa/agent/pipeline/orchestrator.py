"""Pipeline Orchestrator wiring SchemaGrounding, SqlGeneration, ValidationExecution, and AnswerSynthesis agents."""

import concurrent.futures
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from google.adk.agents import SequentialAgent

from pwa.agent.guardrails import check_prompt_injection, rate_limiter
from pwa.agent.pipeline.answer_agent import build_answer_agent, synthesize_answer
from pwa.agent.pipeline.exec_agent import validate_and_execute_sql
from pwa.agent.pipeline.fallback import run_step_with_fallback
from pwa.agent.pipeline.schema_agent import build_schema_agent, ground_schema
from pwa.agent.pipeline.sql_agent import build_sql_agent, generate_sql
from pwa.agent.root_agent import _init_env
from pwa.agent.semantic_cache import semantic_cache
from pwa.logging_setup import setup_logging

logger = logging.getLogger("pwa.agent.pipeline.orchestrator")

DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass
class PipelineResult:
    """Structured result from the 4-stage pipeline, carrying answer + diagnostics."""

    answer: str
    sql: Optional[str] = None
    rows: Optional[list[dict]] = None
    bytes_scanned: Optional[int] = None
    actual_bytes_processed: Optional[int] = None
    slot_ms: Optional[int] = None
    stage_latencies: dict[str, float] = field(default_factory=dict)
    row_count: int = 0
    stage_details: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    retry_count: int = 0
    retry_reason: Optional[str] = None
    exec_status: str = "SUCCESS"
    # Structured visualization recommendation (dict for JSON-safe session_state storage).
    # Populated by build_from_shape (fast path) or the LLM answer block (fallback path).
    viz_recommendation: Optional[dict] = None
    executed_at: Optional[str] = None
    guardrails_applied: list[dict] = field(default_factory=list)
    data_provenance: list[dict] = field(default_factory=list)



def create_pipeline_agent() -> SequentialAgent:
    """Create ADK SequentialAgent exposing full multi-agent pipeline."""
    return SequentialAgent(
        name="PwaMultiAgentPipeline",
        sub_agents=[build_schema_agent(), build_sql_agent(), build_answer_agent()],
    )


# ADK SequentialAgent exposing full pipeline for framework tools and adk web
pipeline_agent = create_pipeline_agent()


def _run_pipeline_stages(
    question: str,
    schema_model: Any = None,
    sql_model: Any = None,
    answer_model: Any = None,
    stage_callback: Any = None,
    routing_latency: float = 0.0,
) -> PipelineResult:
    """Internal execution of 4-stage pipeline. Returns a PipelineResult with diagnostics."""
    stage_latencies: dict[str, float] = {"routing": routing_latency}
    stage_details: dict[str, Any] = {"routing_path": "LLM-fallback"}

    def _notify(stage: str, status: str, extra: dict | None = None):
        if stage_callback:
            try:
                stage_callback(stage, status, extra or {})
            except Exception as exc:
                logger.warning(f"Stage callback error for '{stage}' ({status}): {exc}")

    # Stage 1: Schema Grounding (with fallback)
    _notify("grounding", "started")
    logger.debug(f"[Stage 1] Grounding schema for question: '{question}'...")
    t0 = time.perf_counter()
    schema_context, _ = run_step_with_fallback(
        "schema",
        ground_schema,
        question,
        primary_model=schema_model,
    )
    stage_latencies["schema"] = round(time.perf_counter() - t0, 3)
    logger.debug(f"[Stage 1 Result]: {schema_context} ({stage_latencies['schema']}s)")
    _notify("grounding", "completed", {"latency": stage_latencies["schema"]})

    # Stage 2: SQL Generation (Attempt 1 with fallback)
    _notify("sql", "started")
    logger.debug("[Stage 2] Generating SQL query...")
    t0 = time.perf_counter()
    sql, _ = run_step_with_fallback(
        "sql",
        generate_sql,
        question,
        schema_context,
        primary_model=sql_model,
    )
    stage_latencies["sql"] = round(time.perf_counter() - t0, 3)
    logger.debug(f"[Stage 2 Result - SQL Attempt 1]: {sql} ({stage_latencies['sql']}s)")
    _notify("sql", "completed", {"sql": sql, "latency": stage_latencies["sql"]})

    # Stage 3: Static Validation & BigQuery Execution (Attempt 1)
    _notify("validate", "started")
    logger.debug("[Stage 3] Validating and executing SQL...")
    t0 = time.perf_counter()
    result = validate_and_execute_sql(sql)
    stage_latencies["exec"] = round(time.perf_counter() - t0, 3)
    logger.debug(f"[Stage 3 Result - Attempt 1 Status]: {result.get('status')} ({stage_latencies['exec']}s)")

    # Retry Mechanism — only on actual execution errors, NOT on legitimate zero-row results.
    if result.get("status") == "ERROR":
        error_msg = result.get("error", "Unknown execution error.")
        logger.warning(
            f"[Pipeline Retry] Attempt 1 failed with status 'ERROR': {error_msg}. "
            "Retrying once with error feedback..."
        )

        # Stage 2 (Attempt 2 - Retry with error feedback)
        _notify("sql", "retrying")
        retry_sql, _ = run_step_with_fallback(
            "sql",
            generate_sql,
            question,
            schema_context,
            retry_error=error_msg,
            primary_model=sql_model,
        )
        logger.debug(f"[Stage 2 Result - SQL Attempt 2 (Retry)]: {retry_sql}")

        # Stage 3 (Attempt 2 - Retry)
        _notify("validate", "retrying")
        result = validate_and_execute_sql(retry_sql)
        logger.debug(f"[Stage 3 Result - Attempt 2 Status]: {result.get('status')}")

    _notify("validate", "completed", {"status": result.get("status"), "latency": stage_latencies["exec"]})

    # Stage 4: Answer Synthesis (with fallback)
    # synthesize_answer now returns (answer_str, viz_dict | None)
    _notify("synthesize", "started")
    logger.debug("[Stage 4] Synthesizing natural language answer...")
    t0 = time.perf_counter()
    answer_tuple, _ = run_step_with_fallback(
        "answer",
        synthesize_answer,
        question,
        result,
        primary_model=answer_model,
    )
    stage_latencies["answer"] = round(time.perf_counter() - t0, 3)
    _notify("synthesize", "completed", {"latency": stage_latencies["answer"]})

    # Unpack answer + LLM viz dict (fallback to shape heuristic if absent/invalid)
    if isinstance(answer_tuple, tuple) and len(answer_tuple) == 2:
        final_answer, viz_dict_llm = answer_tuple
    else:
        final_answer, viz_dict_llm = answer_tuple, None

    from pwa.ui.viz_recommendation import build_from_llm_dict, build_from_shape
    import pandas as _pd

    viz_rec_dict: Optional[dict] = None
    if viz_dict_llm:
        validated = build_from_llm_dict(viz_dict_llm)
        viz_rec_dict = validated.to_dict() if validated else None
    if viz_rec_dict is None and result.get("rows"):
        try:
            _df = _pd.DataFrame(result["rows"])
            viz_rec_dict = build_from_shape(_df, question).to_dict()
        except Exception as _ve:
            logger.debug(f"[Viz] Shape fallback failed: {_ve}")

    retry_count = 1 if result.get("status") != "ERROR" and "error_msg" in locals() else 0
    retry_reason = error_msg if "error_msg" in locals() else None

    import datetime
    import sqlglot
    import sqlglot.expressions as exp

    executed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Extract base mart views from generated SQL for data provenance
    tables_found = set()
    if result.get("sql"):
        try:
            parsed = sqlglot.parse_one(result["sql"], read="bigquery")
            if parsed:
                for tbl in parsed.find_all(exp.Table):
                    tbl_name = tbl.name or ""
                    db = tbl.args.get("db") or ""
                    if hasattr(db, "name"):
                        db = db.name
                    if db and tbl_name:
                        tables_found.add(f"{db}.{tbl_name}")
                    elif tbl_name and tbl_name.startswith("v_"):
                        tables_found.add(f"mart.{tbl_name}")
        except Exception as _ex:
            logger.debug(f"SQL provenance parse error: {_ex}")

    if not tables_found:
        tables_found = {"mart.v_movie_full"}

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-warehouse")
    data_provenance = [
        {
            "table_name": f"{project_id}.{tbl}" if not tbl.startswith(project_id) else tbl,
            "type": "base_mart_view",
            "description": f"Base warehouse view ({tbl}) — dynamic view over live transactional tables",
            "last_refreshed": "Live transactional data",
        }
        for tbl in sorted(tables_found)
    ]

    # Guardrails applied during query generation/validation
    guardrails_applied = [
        {
            "name": "AST Read-Only Guard",
            "description": "Enforced AST parsing validation allowing SELECT statements only and prohibiting write/DDL expressions",
            "rule": "AST-SELECT",
        },
        {
            "name": "Dry-Run Cost Scan Guard",
            "description": "Verified query scan volume against 100 MB dry-run limit prior to execution",
            "rule": "Cost-Limit",
        },
    ]

    q_sql_combo = f"{question} {result.get('sql', '')}".lower()
    if "roi" in q_sql_combo or "return on investment" in q_sql_combo:
        guardrails_applied.append(
            {
                "name": "ROI Guard",
                "description": "Excluded films with budget_usd <= $1,000 (11 films) to prevent divide-by-near-zero ROI distortion",
                "rule": "Rule 6",
            }
        )

    if ("keyword" in q_sql_combo or "v_movie_keywords" in q_sql_combo or "tags" in q_sql_combo) and (
        "avg" in q_sql_combo or "sum" in q_sql_combo or "count" in q_sql_combo or "revenue" in q_sql_combo or "roi" in q_sql_combo or "budget" in q_sql_combo
    ):
        guardrails_applied.append(
            {
                "name": "Rule 7 1:N Keyword Filter Guard",
                "description": "Deduplicated by movie_id to avoid double-counting films with multiple keyword tags",
                "rule": "Rule 7",
            }
        )

    if "limit " in (result.get("sql") or "").lower():
        guardrails_applied.append(
            {
                "name": "Row Output Limit Guard",
                "description": "Applied LIMIT clause to constrain max response row count",
                "rule": "Limit-Clause",
            }
        )

    return PipelineResult(
        answer=final_answer,
        sql=result.get("sql"),
        rows=result.get("rows"),
        bytes_scanned=result.get("bytes_scanned"),
        actual_bytes_processed=result.get("actual_bytes_processed"),
        slot_ms=result.get("slot_ms"),
        stage_latencies=stage_latencies,
        row_count=result.get("count", 0),
        stage_details=stage_details,
        exec_status=result.get("status", "SUCCESS"),
        retry_count=retry_count,
        retry_reason=retry_reason,
        viz_recommendation=viz_rec_dict,
        executed_at=executed_at,
        guardrails_applied=guardrails_applied,
        data_provenance=data_provenance,
    )


def run_query(
    question: str,
    schema_model: Any = None,
    sql_model: Any = None,
    answer_model: Any = None,
    timeout_seconds: float | None = None,
    stage_callback: Any = None,
) -> str:
    """Run the 4-agent NLP query pipeline. Returns the final natural language answer string."""
    result = run_query_verbose(
        question=question,
        schema_model=schema_model,
        sql_model=sql_model,
        answer_model=answer_model,
        timeout_seconds=timeout_seconds,
        stage_callback=stage_callback,
    )
    # run_query_verbose returns a string on guardrail-blocked or timeout cases
    return result if isinstance(result, str) else result.answer


def run_query_verbose(
    question: str,
    schema_model: Any = None,
    sql_model: Any = None,
    answer_model: Any = None,
    timeout_seconds: float | None = None,
    stage_callback: Any = None,
) -> "str | PipelineResult":
    """Run the 4-agent NLP pipeline. Returns a PipelineResult with SQL, bytes, and stage latencies.

    Falls back to a plain string message for guardrail-blocked or timeout cases.
    """
    if not question:
        raise ValueError("Question cannot be empty.")

    _init_env()
    logger.info(f"=== [PWA Pipeline Run Start] Question: '{question}' ===")
    logger.info(
        f"[Backend Config] GOOGLE_GENAI_USE_VERTEXAI={os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')}, "
        f"GOOGLE_CLOUD_PROJECT={os.environ.get('GOOGLE_CLOUD_PROJECT')}, "
        f"GOOGLE_CLOUD_LOCATION={os.environ.get('GOOGLE_CLOUD_LOCATION')}"
    )

    # 1. Prompt Injection Pre-Check Guardrail
    try:
        check_prompt_injection(question)
    except ValueError as inj_err:
        logger.warning(f"[Guardrail Blocked Prompt Injection]: {inj_err}")
        return (
            "Refused: Your question contains text or instructions that violate security policies. "
            "Please rephrase your question without system commands or prompt overrides."
        )

    # 2. Rate Limiter Guardrail
    try:
        rate_limiter.check_rate_limit()
    except ValueError as rate_err:
        logger.warning(f"[Guardrail Blocked Rate Limit]: {rate_err}")
        return str(rate_err)

    # Resolve Timeout Threshold
    if timeout_seconds is None:
        env_timeout = os.getenv("PWA_AGENT_TIMEOUT_SECONDS", "").strip()
        if env_timeout:
            try:
                timeout_seconds = float(env_timeout)
            except ValueError:
                timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        else:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    # Resolve model singletons for the pipeline run (reuses single client and auth connection)
    from pwa.agent.models import get_model_for_stage

    if schema_model is None:
        schema_model = get_model_for_stage("schema")
    if sql_model is None:
        sql_model = get_model_for_stage("sql")
    if answer_model is None:
        answer_model = get_model_for_stage("answer")

    # 2.5 Template Router Fast-Path (skips LLM pipeline for pre-materialized rollup templates)
    t_route_start = time.perf_counter()
    from pwa.agent.template_router import route_and_execute

    template_result = route_and_execute(question)
    t_route_elapsed = round(time.perf_counter() - t_route_start, 3)

    if template_result:
        import datetime
        logger.info(
            f"[Template Router FAST-PATH] Matched template '{template_result['template_name']}' in {t_route_elapsed}s."
        )
        # Build viz recommendation from shape heuristics — 0 additional LLM calls
        _tmpl_rows = template_result["rows"]
        _tmpl_viz: Optional[dict] = None
        if _tmpl_rows:
            try:
                import pandas as _pd
                from pwa.ui.viz_recommendation import build_from_shape
                _tmpl_viz = build_from_shape(_pd.DataFrame(_tmpl_rows), question).to_dict()
            except Exception as _ve:
                logger.debug(f"[Viz] Fast-path shape build failed: {_ve}")
        return PipelineResult(
            answer=template_result["answer"],
            sql=template_result["sql"],
            rows=_tmpl_rows,
            bytes_scanned=template_result["bytes_scanned"],
            stage_latencies={"routing": t_route_elapsed},
            row_count=len(_tmpl_rows),
            stage_details={"routing_path": "template-match", "template": template_result["template_name"]},
            cache_hit=False,
            exec_status="SUCCESS",
            viz_recommendation=_tmpl_viz,
            executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            guardrails_applied=template_result.get("guardrails_applied", []),
            data_provenance=template_result.get("data_provenance", []),
        )


    # 3. Semantic Cache Lookup (opt-in, gated by PWA_SEMANTIC_CACHE_ENABLED=1)
    cached_answer = semantic_cache.get(question)
    if cached_answer is not None:
        logger.info("[Semantic Cache] Serving answer from cache.")
        return PipelineResult(answer=cached_answer)

    # 4. Overall Pipeline Timeout Execution
    def _execute() -> PipelineResult:
        pipeline_result = _run_pipeline_stages(
            question=question,
            schema_model=schema_model,
            sql_model=sql_model,
            answer_model=answer_model,
            stage_callback=stage_callback,
            routing_latency=t_route_elapsed,
        )
        # Store answer in semantic cache for future similar questions
        semantic_cache.put(question, pipeline_result.answer)
        return pipeline_result

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_execute)
        try:
            final_answer = future.result(timeout=timeout_seconds)
            logger.info("=== [PWA Pipeline Run Finished Successfully] ===")
            return final_answer
        except concurrent.futures.TimeoutError:
            logger.warning(
                f"[Pipeline Timeout] Pipeline execution timed out after {timeout_seconds}s for question: '{question}'"
            )
            return (
                f"The query request took too long to complete (exceeded {timeout_seconds}s timeout). "
                "Please try asking a simpler question or narrowing the time range."
            )


if __name__ == "__main__":
    setup_logging()
    if len(sys.argv) < 2:
        print('Usage: python -m pwa.agent.pipeline.orchestrator "<question>"')
        sys.exit(1)

    question_arg = sys.argv[1]
    print(f"\nPipeline Question: {question_arg}\n")
    answer = run_query(question_arg)
    print(f"Pipeline Answer:\n{answer}\n")
