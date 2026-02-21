import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings

# Context variable for Trace ID
_trace_id_ctx_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

def get_trace_id() -> Optional[str]:
    return _trace_id_ctx_var.get()

def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx_var.set(trace_id)

def generate_trace_id() -> str:
    """Generate a new Trace ID if one doesn't exist in context."""
    tid = str(uuid.uuid4())
    set_trace_id(tid)
    return tid

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def format(self, record: logging.LogRecord) -> str:
        trace_id = get_trace_id()
        
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "trace_id": trace_id,
            "file": record.filename,
            "line": record.lineno,
        }
        
        # Add extra fields from record if available
        if hasattr(record, "extra_data"):
            log_record["data"] = record.extra_data

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)

def setup_logging():
    """
    Configure the root logger to output JSON to stdout.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler(sys.stdout)
    
    if settings.log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s] [TraceID:%(trace_id)s] %(message)s'
        )
        
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Prevent propagation for some noisy libraries if needed
    logging.getLogger("uvicorn.access").propagate = False

# Initialize logging on import
setup_logging()
logger = logging.getLogger("vagent")
