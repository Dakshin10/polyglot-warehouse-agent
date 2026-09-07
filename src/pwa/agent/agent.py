"""Alias module pointing to 4-agent pipeline for ADK web UI discovery."""

from pwa.agent.pipeline.orchestrator import pipeline_agent, run_query

agent = pipeline_agent
root_agent = pipeline_agent

__all__ = ["agent", "pipeline_agent", "root_agent", "run_query"]
