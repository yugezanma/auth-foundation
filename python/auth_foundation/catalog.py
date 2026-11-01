"""カタログの確認(spec/vectors.schema.md §2)。"""

VERBS = ("view", "create", "edit", "approve")
REQUIRED_FEATURES = ("member", "audit")
AUDIENCES = ("internal", "partner", "owner")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate_catalog(catalog):
    """カタログの誤りの配列を返す(誤りが無ければ空)。"""
    out = []
    features = catalog.get("features") or {}
    for f, actions in features.items():
        seen = set()
        for a in actions:
            if a not in VERBS:
                out.append({"code": "invalid_action", "feature": f, "action": a})
            elif a in seen:
                out.append({"code": "duplicate_action", "feature": f, "action": a})
            seen.add(a)
    for f in REQUIRED_FEATURES:
        if f not in features:
            out.append({"code": "missing_required_feature", "feature": f})
    keys = set()
    for r in catalog.get("roles") or []:
        key = r.get("key")
        if key in keys:
            out.append({"code": "duplicate_role", "role": key})
        keys.add(key)
        if r.get("audience") not in AUDIENCES:
            out.append({"code": "invalid_audience", "role": key})
        if not _is_int(r.get("rank")):
            out.append({"code": "invalid_rank", "role": key})
        for f, actions in (r.get("perms") or {}).items():
            if f not in features:
                out.append({"code": "unknown_feature", "role": key, "feature": f})
                continue
            for a in actions:
                if a not in features[f]:
                    out.append({"code": "unknown_action", "role": key, "feature": f, "action": a})
    return out
