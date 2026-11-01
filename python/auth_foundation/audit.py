"""監査ログの形(docs/設計.md §4、spec/vectors.schema.md §6)。保存・検索は各アプリで行う。"""
import re

from ._time import parse_time
from .errors import AuthFoundationError

# spec/audit-actions.json と同じ一覧(テストで突き合わせる)。(名前, 必須か, 保存期間, 予約か)
ACTIONS = (
    ('auth.login.succeeded', True, '13_months', False),
    ('auth.login.failed', True, '13_months', False),
    ('auth.logout', False, '13_months', False),
    ('auth.password.changed', True, '13_months', False),
    ('auth.password.reset', True, '13_months', False),
    ('member.created', True, 'indefinite', False),
    ('member.updated', True, 'indefinite', False),
    ('member.suspended', True, 'indefinite', False),
    ('member.reactivated', True, 'indefinite', False),
    ('member.password_set', True, 'indefinite', False),
    ('member.invited', True, 'indefinite', False),
    ('assignment.created', True, 'indefinite', False),
    ('assignment.updated', True, 'indefinite', False),
    ('assignment.revoked', True, 'indefinite', False),
    ('role.changed', False, 'indefinite', False),
    ('team.created', True, 'indefinite', False),
    ('team.updated', True, 'indefinite', False),
    ('team.archived', True, 'indefinite', False),
    ('team.member_added', True, 'indefinite', False),
    ('team.member_removed', True, 'indefinite', False),
    ('site.created', True, 'indefinite', False),
    ('site.archived', True, 'indefinite', False),
    ('site.unarchived', True, 'indefinite', False),
    ('collaboration.invited', False, 'indefinite', True),
    ('collaboration.accepted', False, 'indefinite', True),
    ('collaboration.suspended', False, 'indefinite', True),
    ('collaboration.ended', False, 'indefinite', True),
    ('report.published', False, 'indefinite', True),
    ('report.unpublished', False, 'indefinite', True),
    ('view_as.started', False, 'indefinite', True),
)
# (正規表現, 必須か, 保存期間)。ACTIONS に無い名前に、上から順に当てる
PATTERNS = (
    ('^[a-z][a-z0-9_]*\\.(archived|unarchived)$', True, 'indefinite'),
    ('^app(\\.[a-z][a-z0-9_]*)+$', False, '13_months'),
)

_BY_NAME = {a[0]: a for a in ACTIONS}
_COMPILED = [(re.compile(p[:-1] + r"\Z" if p.endswith("$") else p), req, ret) for p, req, ret in PATTERNS]

# (項目, 必須か, 型)
FIELDS = (
    ("id", False, "id"),
    ("host_tenant_id", True, "str"),
    ("actor_user_id", False, "str"),
    ("actor_tenant_id", True, "str"),
    ("action", True, "action"),
    ("target_type", True, "str"),
    ("target_id", True, "str"),
    ("before", False, "obj"),
    ("after", False, "obj"),
    ("ip_address", False, "str"),
    ("created_at", True, "time"),
)
_FIELD_NAMES = tuple(f[0] for f in FIELDS)
SECRET_WORDS = ("password", "passwd", "secret", "token", "session", "otp")


def _lookup(action):
    if not isinstance(action, str):
        return None
    if action in _BY_NAME:
        a = _BY_NAME[action]
        return {"required": a[1], "retention": a[2]}
    for rx, req, ret in _COMPILED:
        if rx.match(action):
            return {"required": req, "retention": ret}
    return None


def audit_retention(action):
    """操作名の保存期間("indefinite" か "13_months")。"""
    info = _lookup(action)
    if info is None:
        raise AuthFoundationError("unknown_action", action)
    return info["retention"]


def _is_secret(key):
    k = str(key).lower()
    return k == "code" or any(w in k for w in SECRET_WORDS)


def _scan(value, prefix, out):
    if isinstance(value, dict):
        for k, v in value.items():
            name = "%s.%s" % (prefix, k)
            if _is_secret(k):
                out.append({"code": "secret_field", "field": name})
            else:
                _scan(v, name, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _scan(v, "%s.%d" % (prefix, i), out)


def validate_audit_event(event):
    """監査ログの記録の誤りの配列を返す(誤りが無ければ空)。"""
    if not isinstance(event, dict):
        return [{"code": "invalid_type", "field": "event"}]
    out = []
    for name, required, kind in FIELDS:
        v = event.get(name)
        if v is None:
            if required:
                out.append({"code": "missing_field", "field": name})
            continue
        if kind == "time":
            if parse_time(v) is None:
                out.append({"code": "invalid_time", "field": name})
        elif kind == "id":
            if not (isinstance(v, str) or (isinstance(v, int) and not isinstance(v, bool))):
                out.append({"code": "invalid_type", "field": name})
        elif kind == "obj":
            if not isinstance(v, dict):
                out.append({"code": "invalid_type", "field": name})
        else:  # str / action
            if not isinstance(v, str) or (required and v == ""):
                out.append({"code": "invalid_type", "field": name})
            elif kind == "action" and _lookup(v) is None:
                out.append({"code": "unknown_action", "field": name})
    for name in ("before", "after"):
        if isinstance(event.get(name), dict):
            _scan(event[name], name, out)
    for k in event:
        if k not in _FIELD_NAMES:
            out.append({"code": "unknown_field", "field": k})
    return out


def make_audit_event(fields):
    """表の11項目をすべて持つ記録を作る。誤りがあれば invalid_audit_event を投げる。"""
    if not isinstance(fields, dict):
        raise AuthFoundationError("invalid_audit_event", [{"code": "invalid_type", "field": "event"}])
    event = {name: fields.get(name) for name in _FIELD_NAMES}
    if event["actor_tenant_id"] is None:
        event["actor_tenant_id"] = event["host_tenant_id"]
    for k, v in fields.items():
        if k not in event:
            event[k] = v
    errors = validate_audit_event(event)
    if errors:
        raise AuthFoundationError("invalid_audit_event", errors)
    return event
