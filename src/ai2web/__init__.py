"""AI2Web (ai2w) Python SDK.

Describe your website once. AI2Web makes it understandable to every AI.
"""

from .manifest import Manifest, ai2web
from .validator import validate, ValidationResult, Check
from .negotiator import negotiate
from .server import handle
from .safety import is_safe_public_url, assert_safe_public_url, same_origin
from .schema import validate_schema, SchemaResult
from .export import to_llms_txt, to_agent_json
from . import ap2

__version__ = "0.4.1"

__all__ = [
    "Manifest",
    "ai2web",
    "validate",
    "ValidationResult",
    "Check",
    "negotiate",
    "handle",
    "is_safe_public_url",
    "assert_safe_public_url",
    "same_origin",
    "validate_schema",
    "SchemaResult",
    "to_llms_txt",
    "to_agent_json",
    "ap2",
]
