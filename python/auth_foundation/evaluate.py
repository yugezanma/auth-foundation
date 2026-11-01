"""権限の判定(docs/設計.md §3-4〜§3-5、spec/vectors.schema.md §3〜§4)。

副作用を持たない。入力はすべて引数で受け取り、時刻は snapshot["now"] を使う。
"""
from ._time import require_time
from .errors import AuthFoundationError

SCOPE_TYPES = ("org", "site_group", "site", "equipment")
EXCLUSION_TYPES = ("site", "site_group")


def _parse_permission(catalog, permission):
    if not isinstance(permission, str) or permission.count(".") != 1:
        raise AuthFoundationError("unknown_permission", permission)
    f, a = permission.split(".")
    features = catalog.get("features") or {}
    if f not in features or a not in features[f]:
        raise AuthFoundationError("unknown_permission", permission)
    return f, a


def _parse_resource(resource):
    if isinstance(resource, dict):
        t = resource.get("type")
        if t == "org":
            return ("org", None)
        if t == "site" and isinstance(resource.get("id"), str) and resource["id"]:
            return ("site", resource["id"])
    raise AuthFoundationError("invalid_resource", resource)


class _Entry:
    __slots__ = ("assignment_id", "team", "scope_type", "scope_id", "exclusions", "role", "perms")


class _Context:
    """1人分の判定の下ごしらえ。所属・生きている割当を一度だけ求める。"""

    def __init__(self, catalog, snapshot, user_id, resource=None):
        now = require_time(snapshot.get("now"))
        self.sites = {}
        for s in snapshot.get("sites") or []:
            if s.get("id") in self.sites:
                raise AuthFoundationError("duplicate_site", s.get("id"))
            self.sites[s.get("id")] = list(s.get("groups") or [])
        if resource is not None and resource[0] == "site" and resource[1] not in self.sites:
            raise AuthFoundationError("unknown_site", resource[1])
        status = None
        seen = set()
        for m in snapshot.get("memberships") or []:
            uid = m.get("user_id")
            if uid in seen:
                raise AuthFoundationError("duplicate_membership", uid)
            seen.add(uid)
            if uid == user_id:
                status = m.get("status")
        self.member = status == "active"
        self.alive = []
        if not self.member:
            return
        roles = {}
        for r in catalog.get("roles") or []:
            roles.setdefault(r.get("key"), r.get("perms") or {})
        groups = {g.get("id") for g in snapshot.get("groups") or []}
        teams = {}
        for t in snapshot.get("teams") or []:
            teams.setdefault(t.get("id"), t.get("members") or [])
        for a in snapshot.get("assignments") or []:
            p = a.get("principal") or {}
            if p.get("type") == "user" and p.get("id") == user_id:
                team = None
            elif p.get("type") == "team" and user_id in teams.get(p.get("id"), ()):
                team = p.get("id")
            else:
                continue
            e = self._check(a, roles, groups)
            e.team = team
            if self._alive(a, now) and e.scope_type != "equipment":
                self.alive.append(e)

    def _check(self, a, roles, groups):
        if a.get("role") not in roles:
            raise AuthFoundationError("unknown_role", a.get("role"))
        scope = a.get("scope") or {}
        st, sid = scope.get("type"), scope.get("id")
        if st not in SCOPE_TYPES:
            raise AuthFoundationError("invalid_scope", st)
        self._check_target(st, sid, groups)
        excl = []
        for x in a.get("exclusions") or []:
            if x.get("type") not in EXCLUSION_TYPES:
                raise AuthFoundationError("invalid_exclusion", x.get("type"))
            self._check_target(x.get("type"), x.get("id"), groups)
            excl.append((x.get("type"), x.get("id")))
        e = _Entry()
        e.assignment_id = a.get("id")
        e.scope_type, e.scope_id = st, (None if st == "org" else sid)
        e.exclusions = excl
        e.role = a.get("role")
        e.perms = roles[a.get("role")]
        return e

    def _check_target(self, t, i, groups):
        if t == "site" and i not in self.sites:
            raise AuthFoundationError("unknown_site", i)
        if t == "site_group" and i not in groups:
            raise AuthFoundationError("unknown_group", i)

    @staticmethod
    def _alive(a, now):
        # 両方を先に読む(片方で落ちても、もう片方の形の誤りを見逃さない)
        ts = [require_time(a[k]) for k in ("expires_at", "revoked_at") if a.get(k) is not None]
        return all(t > now for t in ts)

    def reaches(self, e, resource):
        if resource[0] == "org":
            return e.scope_type == "org"
        site = resource[1]
        groups = self.sites[site]
        if not (e.scope_type == "org"
                or (e.scope_type == "site_group" and e.scope_id in groups)
                or (e.scope_type == "site" and e.scope_id == site)):
            return False
        for t, i in e.exclusions:
            if (t == "site" and i == site) or (t == "site_group" and i in groups):
                return False
        return True

    def paths(self, f, a, resource):
        return [_path(e) for e in self.alive if a in (e.perms.get(f) or ()) and self.reaches(e, resource)]

    def decide(self, f, a, resource):
        if not self.member:
            return {"allowed": False, "reason": "not_member", "paths": []}
        ps = self.paths(f, a, resource)
        if ps:
            return {"allowed": True, "reason": None, "paths": ps}
        held = any(a in (e.perms.get(f) or ()) for e in self.alive)
        return {"allowed": False, "reason": "out_of_scope" if held else "no_permission", "paths": []}


def _path(e):
    return {"assignment_id": e.assignment_id,
            "via": {"type": "team", "id": e.team} if e.team is not None else None,
            "scope": {"type": e.scope_type, "id": e.scope_id},
            "role": e.role,
            "direct": e.team is None}


def evaluate(catalog, snapshot, user_id, permission, resource):
    """その人がその対象でその権限を持つか。``{"allowed", "reason", "paths"}`` を返す。"""
    f, a = _parse_permission(catalog, permission)
    res = _parse_resource(resource)
    return _Context(catalog, snapshot, user_id, res).decide(f, a, res)


def permissions_at(catalog, snapshot, user_id, resource):
    """その対象で持つ権限すべてと経路。``{feature: {action: [path, ...]}}``。"""
    res = _parse_resource(resource)
    ctx = _Context(catalog, snapshot, user_id, res)
    out = {}
    if not ctx.member:
        return out
    for f, actions in (catalog.get("features") or {}).items():
        for a in actions:
            ps = ctx.paths(f, a, res)
            if ps:
                out.setdefault(f, {})[a] = ps
    return out


def sites_with(catalog, snapshot, user_id, permission):
    """その権限が届く拠点の ID の配列(snapshot["sites"] の順)。"""
    f, a = _parse_permission(catalog, permission)
    ctx = _Context(catalog, snapshot, user_id)
    if not ctx.member:
        return []
    return [sid for sid in ctx.sites if ctx.paths(f, a, ("site", sid))]


def check_guard(catalog, before, after, actor_user_id, guard_permission="member.edit"):
    """変更の前と後をくらべて、違反(no_admin_left・self_lockout)の配列を返す。"""
    f, a = _parse_permission(catalog, guard_permission)

    def holders(snapshot):
        out = set()
        for m in snapshot.get("memberships") or []:
            uid = m.get("user_id")
            if m.get("status") == "active" and \
                    _Context(catalog, snapshot, uid).decide(f, a, ("org", None))["allowed"]:
                out.add(uid)
        return out

    hb, ha = holders(before), holders(after)
    out = []
    if not ha:
        out.append({"code": "no_admin_left"})
    if actor_user_id in hb and actor_user_id not in ha:
        out.append({"code": "self_lockout"})
    return out
