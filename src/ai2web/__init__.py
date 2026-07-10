"""AI2Web (ai2w) Python SDK.

Describe your website once. AI2Web makes it understandable to every AI.
"""

from .manifest import Manifest, ai2web
from .validator import validate, ValidationResult, Check
from .negotiator import negotiate
from .server import handle
from .safety import is_safe_public_url, assert_safe_public_url, same_origin

__version__ = "0.1.0"

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
]
