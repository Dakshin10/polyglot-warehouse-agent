"""Exponential backoff with jitter retry handler for PWA.

Retries transient network/connection failures while failing fast on
deterministic validation, permission, or schema errors.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Type

logger = logging.getLogger("pwa.ingestion.retry")

# Exceptions classified as deterministic (non-retryable)
NON_RETRYABLE_ERRORS: tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    PermissionError,
    FileNotFoundError,
    KeyError,
    AttributeError,
)


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[tuple[Type[Exception], ...]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator applying exponential backoff with jitter to transient operation failures."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            attempt = 0

            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    # Check non-retryable errors
                    if isinstance(exc, NON_RETRYABLE_ERRORS):
                        logger.error(f"[Retry Engine] Non-retryable failure in `{func.__name__}`: {exc}")
                        raise exc

                    if retryable_exceptions and not isinstance(exc, retryable_exceptions):
                        logger.error(f"[Retry Engine] Non-whitelisted exception in `{func.__name__}`: {exc}")
                        raise exc

                    if attempt > max_retries:
                        logger.error(
                            f"[Retry Engine] Exceeded maximum retries ({max_retries}) for `{func.__name__}`: {exc}"
                        )
                        raise exc

                    sleep_time = delay
                    if jitter:
                        sleep_time = delay * (0.5 + random.random())

                    logger.warning(
                        f"[Retry Engine] Transient error in `{func.__name__}` (attempt {attempt}/{max_retries}): {exc}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(sleep_time)
                    delay *= backoff_factor

        return wrapper

    return decorator
