"""Pipeline Orchestrator — Nexora Enterprise Platform Phase 2B Multi-Agent Analytics.

Orchestrates Agent 0 Router -> Fast Path -> Agent 1 Grounding -> Agent 2 SQL Gen ->
Agent 3 Validation & Execution -> Agent 4 Answer Synthesis -> Viz Router.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from pwa.agent.conversation import ConversationContext
from pwa.agent.fast_path import FastPathExecutor
from pwa.agent.pipeline.answer_agent import AnswerSynthesisAgent, AnalyticalAnswer, synthesize_answer
from pwa.agent.pipeline.exec_agent import ValidationExecutionAgent, validate_and_execute_sql
from pwa.agent.pipeline.schema_agent import GroundingAgent, ground_schema
from pwa.agent.pipeline.sql_agent import SqlGenerationAgent, generate_sql
from pwa.agent.router import QueryRouter, QueryCategory
from pwa.agent.semantic_cache import semantic_cache
from pwa.agent.template_router import route_and_execute as template_route_and_execute
from pwa.observability.tracing import traced_stage
from pwa.semantic.result_contract import QueryResult

logger = logging.getLogger("pwa.agent.pipeline.orchestrator")

MAX_AGENT_STEPS = 5
MAX_SQL_REPAIRS = 2


@dataclass
class PipelineResult:
    """Structured result from Phase 2B multi-agent analytical pipeline."""

    answer: str
    analytical_answer: Optional[AnalyticalAnswer] = None
    query_result: Optional[QueryResult] = None
    sql: Optional[str] = None
    rows: Optional[list[dict[str, Any]]] = None
    row_count: int = 0
    bytes_scanned: int = 0
    actual_bytes_processed: Optional[int] = None
    slot_ms: Optional[int] = None
    exec_status: str = "SUCCESS"  # SUCCESS | WARNING | ERROR | CLARIFICATION_REQUIRED | UNSUPPORTED
    routing_category: str = "ANALYTICAL"
    stage_latencies: dict[str, float] = field(default_factory=dict)
    stage_details: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    retry_count: int = 0
    retry_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    viz_recommendation: Optional[dict[str, Any]] = None
    executed_at: Optional[str] = None
    guardrails_applied: list[dict[str, Any]] = field(default_factory=list)
    data_provenance: list[dict[str, Any]] = field(default_factory=list)
    ambiguity_options: list[str] = field(default_factory=list)
    clarification_message: str = ""


class MultiAgentPipelineOrchestrator:
    """Orchestrates multi-agent analytical query pipeline."""

    def __init__(
        self,
        router: QueryRouter | None = None,
        fast_path: FastPathExecutor | None = None,
        grounding_agent: GroundingAgent | None = None,
        sql_agent: SqlGenerationAgent | None = None,
        exec_agent: ValidationExecutionAgent | None = None,
        answer_agent: AnswerSynthesisAgent | None = None,
        context: ConversationContext | None = None,
    ) -> None:
        self.router = router or QueryRouter()
        self.fast_path = fast_path or FastPathExecutor()
        self.grounding_agent = grounding_agent or GroundingAgent()
        self.sql_agent = sql_agent or SqlGenerationAgent()
        self.exec_agent = exec_agent or ValidationExecutionAgent()
        self.answer_agent = answer_agent or AnswerSynthesisAgent()
        self.context = context or ConversationContext()

    def run_pipeline(self, question: str) -> PipelineResult:
        """Run full 4-agent analytical pipeline, backed by the semantic answer cache."""
        # Stage -1: Semantic Cache — serve repeated/near-duplicate questions
        # without re-running the router, grounding, SQL gen, or BigQuery.
        cached_answer = semantic_cache.get(question)
        if cached_answer is not None:
            return PipelineResult(
                answer=cached_answer,
                exec_status="SUCCESS",
                routing_category="SEMANTIC_CACHE",
                cache_hit=True,
            )

        with traced_stage("query", question_length=len(question)):
            result = self._run_pipeline_uncached(question)
        if result.exec_status == "SUCCESS" and result.answer:
            semantic_cache.put(question, result.answer)
        return result

    def _run_pipeline_uncached(self, question: str) -> PipelineResult:
        latencies: dict[str, float] = {}

        # Stage 0: Agent 0 Query Router
        t0 = time.time()
        with traced_stage("router"):
            route_res = self.router.route(question)
        latencies["router"] = round(time.time() - t0, 4)

        if route_res.category == QueryCategory.UNSUPPORTED:
            return PipelineResult(
                answer=route_res.suggested_action,
                exec_status="UNSUPPORTED",
                routing_category=route_res.category.value,
                stage_latencies=latencies,
                warnings=[route_res.reasoning],
            )

        if route_res.category == QueryCategory.AMBIGUOUS:
            return PipelineResult(
                answer=route_res.clarification_message,
                exec_status="CLARIFICATION_REQUIRED",
                routing_category=route_res.category.value,
                stage_latencies=latencies,
                ambiguity_options=route_res.ambiguity_options,
                clarification_message=route_res.clarification_message,
            )

        # Stage 0.2: Phase 2C Analytical Workflow Dispatch
        if route_res.workflow_template_hint:
            try:
                from pwa.analytics.templates import get_workflow_template
                from pwa.analytics.orchestrator import AnalyticalWorkflowOrchestrator

                wf = get_workflow_template(route_res.workflow_template_hint)
                if wf:
                    wf_orch = AnalyticalWorkflowOrchestrator()
                    wf_res = wf_orch.execute_workflow(wf)

                    insights_list = []
                    for i in wf_res.get("insights", []):
                        if isinstance(i, dict):
                            t = i.get("title", "Insight")
                            obs = i.get("observation") or i.get("description") or str(i)
                        else:
                            t = getattr(i, "title", "Insight")
                            obs = getattr(i, "observation", None) or getattr(i, "description", None) or str(i)
                        insights_list.append(f"• **{t}**: {obs}")

                    insights_summary = "\n".join(insights_list)
                    answer_text = f"### Multi-Step Analytical Workflow [{wf.name}]\n\n{wf.description}\n\n**Key Findings & Insights:**\n{insights_summary}"

                    return PipelineResult(
                        answer=answer_text,
                        sql=f"-- Multi-Step Analytical Workflow: {wf.workflow_id}",
                        rows=[
                            {
                                "workflow_run_id": wf_res.get("workflow_run_id"),
                                "completed_steps": len(wf_res.get("completed_step_ids", [])),
                                "insights_generated": len(wf_res.get("insights", [])),
                            }
                        ],
                        row_count=len(wf_res.get("completed_step_ids", [])),
                        bytes_scanned=wf_res.get("total_bytes_processed", 0),
                        exec_status="SUCCESS",
                        routing_category="ANALYTICAL_WORKFLOW",
                        stage_latencies=latencies,
                    )
            except Exception as wf_exc:
                logger.warning(f"Analytical workflow execution error: {wf_exc}, falling through to standard SQL path.")

        # Stage 0.4: Template Router — pre-materialized BigQuery rollup tables.
        # Cheaper than the Stage 0.5 semantic fast path (no live aggregation),
        # so it gets first refusal when it can answer the question. Unlike every
        # other stage, this one has no offline/mock mode (it talks to BigQuery
        # directly), so it is opt-in via env var to keep unit tests network-free.
        template_res = None
        if os.getenv("PWA_ENABLE_TEMPLATE_ROUTER", "0").strip() == "1":
            t0 = time.time()
            with traced_stage("template_router"):
                try:
                    template_res = template_route_and_execute(question)
                except Exception as exc:
                    logger.warning(f"Template router failed, falling through: {exc}")
                    template_res = None
        if template_res:
            latencies["template_router"] = round(time.time() - t0, 4)
            return PipelineResult(
                answer=template_res["answer"],
                sql=template_res.get("sql"),
                rows=template_res.get("rows"),
                row_count=len(template_res.get("rows") or []),
                bytes_scanned=template_res.get("bytes_scanned") or 0,
                exec_status="SUCCESS",
                routing_category="TEMPLATE_ROLLUP",
                stage_latencies=latencies,
                guardrails_applied=template_res.get("guardrails_applied", []),
                data_provenance=template_res.get("data_provenance", []),
            )

        # Stage 0.5: Fast-Path Check
        t0 = time.time()
        with traced_stage("fast_path"):
            fast_res = self.fast_path.match_and_execute(question)
        if fast_res:
            latencies["fast_path"] = round(time.time() - t0, 4)
            if fast_res.rows:
                try:
                    import pandas as pd
                    from pwa.governance.pii import mask_dataframe_pii

                    df_fast = pd.DataFrame(fast_res.rows)
                    masked_fast = mask_dataframe_pii(df_fast)
                    fast_res.rows = masked_fast.to_dict(orient="records")
                except Exception as mask_exc:
                    logger.warning(f"PII FastPath masking error: {mask_exc}")

            analytical_ans = self.answer_agent.synthesize(question, fast_res)
            return PipelineResult(
                answer=analytical_ans.answer_text,
                analytical_answer=analytical_ans,
                query_result=fast_res,
                sql=fast_res.sql,
                rows=fast_res.rows,
                row_count=fast_res.row_count,
                bytes_scanned=fast_res.bytes_processed,
                exec_status="SUCCESS",
                routing_category="FAST_PATH",
                stage_latencies=latencies,
                warnings=fast_res.warnings,
                viz_recommendation=analytical_ans.visualization_spec.__dict__
                if analytical_ans.visualization_spec
                else None,
            )

        # Stage 1: Agent 1 Semantic Grounding
        t0 = time.time()
        with traced_stage("grounding"):
            grounded = self.grounding_agent.ground_question(question)
        latencies["grounding"] = round(time.time() - t0, 4)

        if grounded.clarification_required:
            return PipelineResult(
                answer=grounded.clarification_message,
                exec_status="CLARIFICATION_REQUIRED",
                routing_category="AMBIGUOUS",
                stage_latencies=latencies,
                ambiguity_options=grounded.ambiguities,
                clarification_message=grounded.clarification_message,
            )

        # Check multi-turn context
        merged_intent = self.context.resolve_followup(question, grounded.analytical_intent)

        # Stage 2: Agent 2 Governed SQL Generation
        t0 = time.time()
        with traced_stage("sql_gen"):
            try:
                sql = self.sql_agent.generate_sql_from_intent(merged_intent)
            except Exception as exc:
                logger.error(f"SQL Generation error: {exc}")
                return PipelineResult(
                    answer=f"Could not generate governed SQL: {exc}",
                    exec_status="ERROR",
                    stage_latencies=latencies,
                    warnings=[str(exc)],
                )
        latencies["sql_gen"] = round(time.time() - t0, 4)

        # Stage 3: Agent 3 Validation & Execution (with Bounded Query Repair)
        t0 = time.time()
        query_res: Optional[QueryResult] = None
        exec_error: Optional[str] = None

        with traced_stage("execution"):
            for repair_attempt in range(MAX_SQL_REPAIRS + 1):
                try:
                    query_res = self.exec_agent.validate_and_execute(sql, intent=merged_intent)
                    break
                except Exception as exc:
                    exec_error = str(exc)
                    logger.warning(f"Execution attempt {repair_attempt + 1} failed: {exc}")
                    if repair_attempt < MAX_SQL_REPAIRS:
                        # Attempt query repair
                        try:
                            sql = self.sql_agent.generate_sql_from_intent(merged_intent, prior_error=exec_error)
                        except Exception:
                            pass
        latencies["execution"] = round(time.time() - t0, 4)

        if not query_res:
            return PipelineResult(
                answer=f"Query execution failed after {MAX_SQL_REPAIRS} repair attempts: {exec_error}",
                sql=sql,
                exec_status="ERROR",
                stage_latencies=latencies,
                warnings=[str(exec_error)],
            )

        if query_res and query_res.rows:
            try:
                import pandas as pd
                from pwa.governance.pii import mask_dataframe_pii

                df_rows = pd.DataFrame(query_res.rows)
                masked_df = mask_dataframe_pii(df_rows)
                query_res.rows = masked_df.to_dict(orient="records")
            except Exception as mask_exc:
                logger.warning(f"PII post-execution masking error: {mask_exc}")

        # Stage 4: Agent 4 Answer Synthesis & Visualization Routing
        t0 = time.time()
        with traced_stage("synthesis"):
            analytical_ans = self.answer_agent.synthesize(question, query_res)
        latencies["synthesis"] = round(time.time() - t0, 4)

        # Save turn to conversation memory
        self.context.add_turn(question=question, intent=merged_intent, sql=query_res.sql)

        return PipelineResult(
            answer=analytical_ans.answer_text,
            analytical_answer=analytical_ans,
            query_result=query_res,
            sql=query_res.sql,
            rows=query_res.rows,
            row_count=query_res.row_count,
            bytes_scanned=query_res.bytes_processed,
            exec_status="SUCCESS",
            routing_category=route_res.category.value,
            stage_latencies=latencies,
            warnings=analytical_ans.warnings,
            viz_recommendation=analytical_ans.visualization_spec.__dict__
            if analytical_ans.visualization_spec
            else None,
        )


pipeline_agent = None


def run_step_with_fallback(step_name: str, step_fn: Any, question: str, *args: Any, **kwargs: Any) -> tuple[Any, None]:
    """Legacy helper running step function."""
    res = step_fn(question, *args, **kwargs) if callable(step_fn) else None
    return res, None


_legacy_router = QueryRouter()
_legacy_fast_path = FastPathExecutor()


def _run_pipeline_stages(
    question: str,
    schema_model: Any = None,
    sql_model: Any = None,
    answer_model: Any = None,
    stage_callback: Any = None,
    routing_latency: float = 0.0,
) -> PipelineResult:
    """Legacy 4-stage pipeline execution helper.

    Shares the Agent 0 Router, semantic answer cache, and Fast-Path with the
    class-based `MultiAgentPipelineOrchestrator` so `run_query()` gets the same
    mutation/out-of-scope rejection, ambiguity handling, and zero-cost fast
    paths as `run_query_verbose()` — it should not be a second, lesser pipeline.
    """
    stage_latencies: dict[str, float] = {"routing": routing_latency}

    cached_answer = semantic_cache.get(question)
    if cached_answer is not None:
        return PipelineResult(
            answer=cached_answer, exec_status="SUCCESS", cache_hit=True, stage_latencies=stage_latencies
        )

    route_res = _legacy_router.route(question)
    if route_res.category == QueryCategory.UNSUPPORTED:
        return PipelineResult(
            answer=route_res.suggested_action,
            exec_status="UNSUPPORTED",
            routing_category=route_res.category.value,
            stage_latencies=stage_latencies,
            warnings=[route_res.reasoning],
        )
    if route_res.category == QueryCategory.AMBIGUOUS:
        return PipelineResult(
            answer=route_res.clarification_message,
            exec_status="CLARIFICATION_REQUIRED",
            routing_category=route_res.category.value,
            stage_latencies=stage_latencies,
            ambiguity_options=route_res.ambiguity_options,
            clarification_message=route_res.clarification_message,
        )

    fast_res = _legacy_fast_path.match_and_execute(question)
    if fast_res:
        answer_contract = AnswerSynthesisAgent().synthesize(question, fast_res)
        fast_result = PipelineResult(
            answer=answer_contract.answer_text,
            analytical_answer=answer_contract,
            query_result=fast_res,
            sql=fast_res.sql,
            rows=fast_res.rows,
            row_count=fast_res.row_count,
            bytes_scanned=fast_res.bytes_processed,
            exec_status="SUCCESS",
            routing_category="FAST_PATH",
            stage_latencies=stage_latencies,
            warnings=fast_res.warnings,
        )
        semantic_cache.put(question, fast_result.answer)
        return fast_result

    # Stage 1: Schema Grounding
    schema_context, _ = run_step_with_fallback("schema", ground_schema, question, primary_model=schema_model)

    if isinstance(schema_context, dict) and schema_context.get("clarification_required"):
        return PipelineResult(
            answer=schema_context.get("clarification_message", "Could you clarify your question?"),
            exec_status="CLARIFICATION_REQUIRED",
            stage_latencies=stage_latencies,
            ambiguity_options=schema_context.get("ambiguities", []),
            clarification_message=schema_context.get("clarification_message", ""),
        )

    # Stage 2: SQL Generation (Attempt 1)
    sql, _ = run_step_with_fallback("sql", generate_sql, question, schema_context, primary_model=sql_model)

    # Stage 3: Static Validation & BigQuery Execution (Attempt 1)
    result = validate_and_execute_sql(sql)

    # Retry Mechanism on ERROR
    if isinstance(result, dict) and result.get("status") == "ERROR":
        error_msg = result.get("error", "Execution error")
        retry_sql, _ = run_step_with_fallback(
            "sql", generate_sql, question, schema_context, retry_error=error_msg, primary_model=sql_model
        )
        result = validate_and_execute_sql(retry_sql)

    # Stage 4: Answer Synthesis
    answer, viz = run_step_with_fallback("answer", synthesize_answer, question, result, primary_model=answer_model)

    ans_str = answer if isinstance(answer, str) else getattr(answer, "answer_text", str(answer))

    rows_val = result.get("rows") if isinstance(result, dict) else getattr(result, "rows", None)
    cnt_val = (
        result.get("row_count") or result.get("count") if isinstance(result, dict) else getattr(result, "row_count", 0)
    )
    bytes_val = result.get("bytes_scanned") if isinstance(result, dict) else getattr(result, "bytes_processed", 0)
    exec_status = result.get("status", "SUCCESS") if isinstance(result, dict) else "SUCCESS"

    if exec_status == "SUCCESS" and ans_str:
        semantic_cache.put(question, ans_str)

    return PipelineResult(
        answer=ans_str,
        sql=sql if isinstance(sql, str) else None,
        rows=rows_val,
        row_count=cnt_val or 0,
        bytes_scanned=bytes_val or 0,
        stage_latencies=stage_latencies,
        exec_status=exec_status,
    )


def run_query_verbose(
    question: str, stage_callback: Any = None, timeout_seconds: float = 120.0
) -> PipelineResult | str:
    """Run the full multi-agent pipeline and return the structured PipelineResult.

    `timeout_seconds` is enforced the same (best-effort, post-hoc) way as
    `run_query()`: the pipeline call itself is not interruptible mid-flight,
    but a result that arrives after the deadline is reported as a timeout
    instead of a normal answer, so the benchmark/perf harnesses that pass
    this argument get an honest signal instead of a silent TypeError.
    """
    t0 = time.time()
    orchestrator = MultiAgentPipelineOrchestrator()
    result = orchestrator.run_pipeline(question)
    elapsed = time.time() - t0

    if elapsed > timeout_seconds:
        return f"The query request took too long to complete: exceeded {timeout_seconds}s timeout."

    return result


def run_query(question: str, timeout_seconds: float = 120.0) -> str:
    """Synchronous helper running multi-agent pipeline and returning answer text."""
    try:
        from pwa.agent.guardrails import check_prompt_injection

        check_prompt_injection(question)
    except ValueError:
        return "Refused: Your question contains text or instructions that violate security policies."

    t0 = time.time()
    orchestrator = MultiAgentPipelineOrchestrator()
    res = orchestrator.run_pipeline(question)
    elapsed = time.time() - t0

    if elapsed > timeout_seconds:
        return f"The query request took too long to complete: exceeded {timeout_seconds}s timeout."

    return res.answer
