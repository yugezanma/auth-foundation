"""カタログの確認(spec/vectors.schema.md §2)。"""
from ._shape import get, is_int, items

VERBS = ("view", "create", "edit", "approve")
REQUIRED_FEATURES = ("member", "audit")
AUDIENCES = ("internal", "partner", "owner")


def validate_catalog(catalog):
    """カタログの誤りの配列を返す(誤りが無ければ空)。"""
    out = []
    features = get(catalog, "features")
    features = features if isinstance(features, dict) else {}
    for f, actions in features.items():
        if not isinstance(actions, list):
            out.append({"code": "invalid_list", "feature": f})
            continue
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
    for r in items(get(catalog, "roles")):
        key = get(r, "key")
        if key in keys:
            out.append({"code": "duplicate_role", "role": key})
        keys.add(key)
        if get(r, "audience") not in AUDIENCES:
            out.append({"code": "invalid_audience", "role": key})
        if not is_int(get(r, "rank")):
            out.append({"code": "invalid_rank", "role": key})
        perms = get(r, "perms")
        for f, actions in (perms.items() if isinstance(perms, dict) else ()):
            if f not in features:
                out.append({"code": "unknown_feature", "role": key, "feature": f})
                continue
            if not isinstance(actions, list):
                out.append({"code": "invalid_list", "role": key, "feature": f})
                continue
            for a in actions:
                if a not in items(features[f]):
                    out.append({"code": "unknown_action", "role": key, "feature": f, "action": a})
    return out
