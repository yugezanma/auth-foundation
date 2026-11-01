"""ユーザー管理(認証・権限)の共通の部品。Python 版。

設計は docs/設計.md、細かな決まりは spec/vectors.schema.md。副作用を持たない関数だけを置く。
"""
from .audit import ACTIONS as AUDIT_ACTIONS, PATTERNS as AUDIT_PATTERNS, audit_retention, make_audit_event, validate_audit_event
from .catalog import VERBS, validate_catalog
from .errors import AuthFoundationError
from .evaluate import check_guard, evaluate, permissions_at, sites_with

__version__ = "1.0.0"

__all__ = [
    "AUDIT_ACTIONS", "AUDIT_PATTERNS", "AuthFoundationError", "VERBS", "__version__",
    "audit_retention", "check_guard", "evaluate", "make_audit_event", "permissions_at",
    "sites_with", "validate_audit_event", "validate_catalog",
]
