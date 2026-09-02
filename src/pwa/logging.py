import re
import logging


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
                record.args = {k: self.redact(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.redact(str(arg)) for arg in record.args)
        return True


def setup_logging(level: int = logging.INFO):
    """Configure root logger with structured formatting and redacting filter."""
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
