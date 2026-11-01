"""権限の判定(docs/設計.md §3-4〜§3-5、spec/vectors.schema.md §3〜§4)。

副作用を持たない。入力はすべて引数で受け取り、時刻は snapshot["now"] を使う。
値の形は JS 版と同じ手順で読む(配列でなければ空の配列、オブジェクトでなければ空のオブジェクト)。
"""
from ._shape import get, items
from ._time import require_time
from .errors import AuthFoundationError

SCOPE_TYPES = ("org", "site_group", "site", "equipment")
EXCLUSION_TYPES = ("site", "site_group")


def _parse_permission(catalog, permission):
    if not isinstance(permission, str) or permission.count(".") != 1:
        raise AuthFoundationError("unknown_permission", permission)
    f, a = permission.split(".")
    features = get(catalog, "features")
    if not isinstance(features, dict) or f not in features or a not in items(features[f]):
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


class _Prepared:
    """スナップショット全体の下ごしらえ(拠点・所属・ロール・グループ・チーム)。1回だけ作って使い回す。"""

    def __init__(self, catalog, snapshot):
        self.now = require_time(get(snapshot, "now"))
        self.sites = {}
        for s in items(get(snapshot, "sites")):
            sid = get(s, "id")
            if sid in self.sites:
                raise AuthFoundationError("duplicate_site", sid)
            self.sites[sid] = list(items(get(s, "groups")))
        self.status = {}
        for m in items(get(snapshot, "memberships")):
            uid = get(m, "user_id")
            if uid in self.status:
                raise AuthFoundationError("duplicate_membership", uid)
            self.status[uid] = get(m, "status")
        self.roles = {}
        for r in items(get(catalog, "roles")):
            perms = get(r, "perms")
            self.roles.setdefault(get(r, "key"), perms if isinstance(perms, dict) else {})
        self.groups = {get(g, "id") for g in items(get(snapshot, "groups"))}
        self.teams = {}
        for t in items(get(snapshot, "teams")):
            self.teams.setdefault(get(t, "id"), items(get(t, "members")))
        self.assignments = items(get(snapshot, "assignments"))

    def check_site(self, resource):
        if resource[0] == "site" and resource[1] not in self.sites:
            raise AuthFoundationError("unknown_site", resource[1])

    def active_users(self):
        return [uid for uid, st in self.status.items() if st == "active"]

    def context(self, user_id):
        return _Context(self, user_id)


class _Entry:
    __slots__ = ("assignment_id", "team", "scope_type", "scope_id", "exclusions", "role", "perms")

    def grants(self, f, a):
        return a in items(self.perms.get(f))


class _Context:
    """1人分の判定。生きている割当を一度だけ求める。"""

    def __init__(self, prep, user_id):
        self.prep = prep
        self.sites = prep.sites
        self.member = prep.status.get(user_id) == "active"
        self.alive = []
        if not self.member:
            return
        for a in prep.assignments:
            p = get(a, "principal")
            if get(p, "type") == "user" and get(p, "id") == user_id:
                team = None
            elif get(p, "type") == "team" and user_id in prep.teams.get(get(p, "id"), ()):
                team = get(p, "id")
            else:
                continue
            e = self._check(a)
            e.team = team
            # 両方を先に読む(片方で落ちても、もう片方の形の誤りを見逃さない)
            ts = [require_time(get(a, k)) for k in ("expires_at", "revoked_at") if get(a, k) is not None]
            if all(t > prep.now for t in ts) and e.scope_type != "equipment":
                self.alive.append(e)

    def _check(self, a):
        prep = self.prep
        role = get(a, "role")
        if role not in prep.roles:
            raise AuthFoundationError("unknown_role", role)
        scope = get(a, "scope")
        st, sid = get(scope, "type"), get(scope, "id")
        if st not in SCOPE_TYPES:
            raise AuthFoundationError("invalid_scope", st)
        self._check_target(st, sid)
        excl = []
        for x in items(get(a, "exclusions")):
            t, i = get(x, "type"), get(x, "id")
            if t not in EXCLUSION_TYPES:
                raise AuthFoundationError("invalid_exclusion", t)
            self._check_target(t, i)
            excl.append((t, i))
        e = _Entry()
        e.assignment_id = get(a, "id")
        e.scope_type, e.scope_id = st, (None if st == "org" else sid)
        e.exclusions = excl
        e.role = role
        e.perms = prep.roles[role]
        return e

    def _check_target(self, t, i):
        if t == "site" and i not in self.sites:
            raise AuthFoundationError("unknown_site", i)
        if t == "site_group" and i not in self.prep.groups:
            raise AuthFoundationError("unknown_group", i)

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
        return [_path(e) for e in self.alive if e.grants(f, a) and self.reaches(e, resource)]

    def allows(self, f, a, resource):
        return self.member and any(e.grants(f, a) and self.reaches(e, resource) for e in self.alive)

    def decide(self, f, a, resource):
        if not self.member:
            return {"allowed": False, "reason": "not_member", "paths": []}
        ps = self.paths(f, a, resource)
        if ps:
            return {"allowed": True, "reason": None, "paths": ps}
        held = any(e.grants(f, a) for e in self.alive)
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
    prep = _Prepared(catalog, snapshot)
    prep.check_site(res)
    return prep.context(user_id).decide(f, a, res)


def permissions_at(catalog, snapshot, user_id, resource):
    """その対象で持つ権限すべてと経路。``{feature: {action: [path, ...]}}``。"""
    res = _parse_resource(resource)
    prep = _Prepared(catalog, snapshot)
    prep.check_site(res)
    ctx = prep.context(user_id)
    out = {}
    if not ctx.member:
        return out
    features = get(catalog, "features")
    for f, actions in (features.items() if isinstance(features, dict) else ()):
        for a in items(actions):
            ps = ctx.paths(f, a, res)
            if ps:
                out.setdefault(f, {})[a] = ps
    return out


def sites_with(catalog, snapshot, user_id, permission):
    """その権限が届く拠点の ID の配列(snapshot["sites"] の順)。"""
    f, a = _parse_permission(catalog, permission)
    ctx = _Prepared(catalog, snapshot).context(user_id)
    return [sid for sid in ctx.sites if ctx.allows(f, a, ("site", sid))]


def check_guard(catalog, before, after, actor_user_id, guard_permission="member.edit"):
    """変更の前と後をくらべて、違反(no_admin_left・self_lockout)の配列を返す。"""
    f, a = _parse_permission(catalog, guard_permission)

    def holders(snapshot):
        prep = _Prepared(catalog, snapshot)
        return {uid for uid in prep.active_users() if prep.context(uid).allows(f, a, ("org", None))}

    hb, ha = holders(before), holders(after)
    out = []
    if not ha:
        out.append({"code": "no_admin_left"})
    if actor_user_id in hb and actor_user_id not in ha:
        out.append({"code": "self_lockout"})
    return out
