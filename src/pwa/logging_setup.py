import logging
import re
import socket


class RedactingFilter(logging.Filter):
    """Filter that redacts passwords and DSN credentials in log messages and tracebacks."""

    PATTERNS = [
        re.compile(r":([^/@:]+)@"),  # DSN passwords :pass@
        re.compile(r'password=["\']?[^"\'\s]+["\']?', re.I),  # password='xyz'
        re.compile(r'secret=["\']?[^"\'\s]+["\']?', re.I),  # secret='xyz'
    ]

    def redact(self, text: str) -> str:
        if not text:
            return ""
        s = str(text)
        s = re.sub(r":([^/@:]+)@", r":****@", s)
        s = re.sub(r'(password=[\'"]?)[^\'"\s]+([\'"]?)', r"\1****\2", s, flags=re.I)
        s = re.sub(r'(secret=[\'"]?)[^\'"\s]+([\'"]?)', r"\1****\2", s, flags=re.I)
        return s

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg:
            record.msg = self.redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


_IPV4_PATCH_APPLIED = False


def apply_ipv4_only_patch() -> None:
    """Force IPv4-only DNS resolution across the process to prevent 20s+ IPv6 fallback timeouts."""
    global _IPV4_PATCH_APPLIED
    if _IPV4_PATCH_APPLIED:
        return

    try:
        import urllib3.util.connection

        urllib3.util.connection.HAS_IPV6 = False
    except Exception:
        pass

    _orig_getaddrinfo = socket.getaddrinfo

    def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0 or family == socket.AF_UNSPEC:
            family = socket.AF_INET
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo_ipv4_only
    _IPV4_PATCH_APPLIED = True


def setup_logging(level: int = logging.INFO):
    """Configure root logger with structured formatting and redacting filter."""
    apply_ipv4_only_patch()
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())

    root.addHandler(handler)
