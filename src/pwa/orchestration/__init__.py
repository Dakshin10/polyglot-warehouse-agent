"""Dagster orchestration for the PWA ingestion → warehouse → rollup pipeline.

Before this, `pwa source run`, `pwa warehouse run`, and `pwa refresh-rollups`
were CLI verbs a human (or a naive cron) had to invoke by hand, in the right
order, with no automatic retry, no dependency graph between stages, and no
alert if one silently failed at 3am. This package wraps the exact same
underlying functions in a real asset graph with retries and failure alerting,
runnable locally with `dagster dev -m pwa.orchestration` or deployed to
Dagster+/OSS the same way as any other Dagster project.
"""
