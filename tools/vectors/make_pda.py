"""電力データ集計(power-data-app の feature/user-management)の今の判定を、共通の形に当てはめた判定テストを書き出す。

正解は、電力データ集計の app/core/auth.py の決まりをこのスクリプトに書き写して作る(共通の部品からは作らない):
  - is_admin(user)          = 有効 かつ role == admin
  - can_operate(user, cid)  = is_admin(user) または (有効 かつ role == creator かつ cid が担当契約)
  - 閲覧(契約一覧・月次作業画面・履歴・契約マスタを見る)は有効なユーザー全員
  - 契約マスタの保存・ユーザー管理は管理者だけ
割当への当てはめは docs/設計.md §7-3。

使い方: python3 tools/vectors/make_pda.py spec/vectors
"""
import json, os, sys

OUT = sys.argv[1]
SITES = ["A", "B", "C", "D", "E", "F"]
USERS = [  # (ユーザーID, 画面のロール, 担当契約, 有効か)
    ("admin", "admin", [], True),
    ("sakusei1", "creator", ["A", "C", "E"], True),
    ("sakusei2", "creator", ["B", "D", "F"], True),
    ("etsuran", "viewer", [], True),
    ("sakusei3", "creator", [], True),     # 担当契約が0件の作成者
    ("muko", "creator", ["A"], False),     # 無効にしたユーザー
]

CATALOG = {
    "features": {"report": ["view", "edit"], "site_master": ["view", "create", "edit"],
                 "member": ["view", "create", "edit"], "audit": ["view"]},
    "roles": [
        {"key": "admin", "rank": 3, "audience": "internal", "perms": {
            "report": ["view", "edit"], "site_master": ["view", "create", "edit"],
            "member": ["view", "create", "edit"], "audit": ["view"]}},
        {"key": "creator", "rank": 2, "audience": "internal", "perms": {"report": ["view", "edit"]}},
        {"key": "viewer", "rank": 1, "audience": "internal", "perms": {"report": ["view"], "site_master": ["view"]}},
    ],
}


def assignments_for(uid, role, contracts):
    """画面のロールと担当契約から割当を作る(設計.md §7-3)。"""
    out = []
    if role == "admin":
        out.append(("%s@org" % uid, "admin", {"type": "org", "id": None}))
    elif role == "creator":
        for c in contracts:
            out.append(("%s@%s" % (uid, c), "creator", {"type": "site", "id": c}))
        out.append(("%s@org" % uid, "viewer", {"type": "org", "id": None}))
    else:
        out.append(("%s@org" % uid, "viewer", {"type": "org", "id": None}))
    return out


ASSIGN = []
BY_USER = {}
for uid, role, contracts, active in USERS:
    rows = assignments_for(uid, role, contracts)
    BY_USER[uid] = rows
    for aid, r, scope in rows:
        ASSIGN.append({"id": aid, "principal": {"type": "user", "id": uid}, "role": r, "scope": scope,
                       "exclusions": [], "expires_at": None, "revoked_at": None,
                       "granted_by": "admin", "created_at": "2026-10-29T09:00:00+09:00"})

SNAPSHOT = {
    "tenant_id": "demo", "now": "2026-11-01T09:00:00+09:00",
    "sites": [{"id": s, "groups": []} for s in SITES], "groups": [],
    "memberships": [{"user_id": u, "status": "active" if a else "suspended"} for u, _, _, a in USERS],
    "teams": [], "assignments": ASSIGN,
}


def path(aid, role, scope):
    return {"assignment_id": aid, "via": None, "scope": scope, "role": role, "direct": True}


# ---- 電力データ集計の決まり(auth.py の書き写し)
def pda_allowed(uid, role, contracts, active, perm, site):
    if not active:
        return False
    is_admin = role == "admin"
    if perm in ("report.view", "site_master.view"):
        return True
    if perm == "report.edit":
        return is_admin or (role == "creator" and site in contracts)
    return is_admin  # site_master.create / edit、member.*、audit.view


def expected(uid, role, contracts, active, perm, site):
    if not active:
        return {"allowed": False, "reason": "not_member", "paths": []}
    if pda_allowed(uid, role, contracts, active, perm, site):
        # 経路: その権限を持つロールの割当のうち、対象に届くもの(割当の順)
        rolemap = {r["key"]: r["perms"] for r in CATALOG["roles"]}
        f, a = perm.split(".")
        ps = []
        for aid, r, scope in BY_USER[uid]:
            reach = scope["type"] == "org" or (site is not None and scope["id"] == site)
            if reach and a in rolemap[r].get(f, []):
                ps.append(path(aid, r, scope))
        return {"allowed": True, "reason": None, "paths": ps}
    # 断る理由: 作成者が担当外の契約を操作 → out_of_scope、それ以外 → no_permission
    if perm == "report.edit" and role == "creator" and contracts:
        return {"allowed": False, "reason": "out_of_scope", "paths": []}
    return {"allowed": False, "reason": "no_permission", "paths": []}


cases = []
SITE_PERMS = ["report.view", "report.edit", "site_master.view", "site_master.edit"]
ORG_PERMS = ["site_master.create", "member.view", "member.create", "member.edit", "audit.view"]
for uid, role, contracts, active in USERS:
    for perm in SITE_PERMS:
        for s in SITES:
            cases.append({"name": "%s / %s / 契約%s" % (uid, perm, s), "call": "evaluate",
                          "args": {"user_id": uid, "permission": perm, "resource": {"type": "site", "id": s}},
                          "expect": expected(uid, role, contracts, active, perm, s)})
    for perm in ORG_PERMS:
        cases.append({"name": "%s / %s / 組織全体" % (uid, perm), "call": "evaluate",
                      "args": {"user_id": uid, "permission": perm, "resource": {"type": "org"}},
                      "expect": expected(uid, role, contracts, active, perm, None)})
    for perm in ["report.edit", "report.view"]:
        cases.append({"name": "%s / 操作できる契約(%s)" % (uid, perm), "call": "sites_with",
                      "args": {"user_id": uid, "permission": perm},
                      "expect": [s for s in SITES if pda_allowed(uid, role, contracts, active, perm, s)]})


def snap_with(memberships=None, assignments=None):
    s = json.loads(json.dumps(SNAPSHOT))
    if memberships is not None: s["memberships"] = memberships
    if assignments is not None: s["assignments"] = assignments
    return s


admin_as_viewer = [a for a in ASSIGN if a["id"] != "admin@org"] + [
    {**[a for a in ASSIGN if a["id"] == "admin@org"][0], "id": "admin@org", "role": "viewer"}]
two_admins = ASSIGN + [{**ASSIGN[0], "id": "sakusei1@org-admin", "principal": {"type": "user", "id": "sakusei1"}}]
cases += [
    {"name": "ただ1人の管理者が自分を閲覧にする", "call": "check_guard",
     "args": {"before": SNAPSHOT, "after": snap_with(assignments=admin_as_viewer), "actor_user_id": "admin"},
     "expect": [{"code": "no_admin_left"}, {"code": "self_lockout"}]},
    {"name": "ただ1人の管理者が自分を無効にする", "call": "check_guard",
     "args": {"before": SNAPSHOT, "after": snap_with(memberships=[
         {"user_id": u, "status": "active" if (a and u != "admin") else "suspended"} for u, _, _, a in USERS]),
         "actor_user_id": "admin"},
     "expect": [{"code": "no_admin_left"}, {"code": "self_lockout"}]},
    {"name": "管理者が作成者を無効にする", "call": "check_guard",
     "args": {"before": SNAPSHOT, "after": snap_with(memberships=[
         {"user_id": u, "status": "active" if (a and u != "sakusei1") else "suspended"} for u, _, _, a in USERS]),
         "actor_user_id": "admin"},
     "expect": []},
    {"name": "管理者が2人いれば、1人が自分を閲覧にしても管理者は残る(ただし自分の締め出し)", "call": "check_guard",
     "args": {"before": snap_with(assignments=two_admins),
              "after": snap_with(assignments=[a if a["id"] != "admin@org" else {**a, "role": "viewer"} for a in two_admins]),
              "actor_user_id": "admin"},
     "expect": [{"code": "self_lockout"}]},
]

doc = {"name": "pda",
       "description": "電力データ集計の今の判定(app/core/auth.py の can_operate・is_admin と断る理由)を、共通の形(設計.md §7)に当てはめたもの。"
                      "sakusei3 は担当契約が0件の作成者で、割当だけでは閲覧と同じ no_permission になる(文言は画面のロールでアプリが選ぶ)。muko は無効にしたユーザー。"
                      "テナントはデモの会社 demo(設計.md §7-4)。会社ごとのスナップショットの1つに当たる",
       "catalog": CATALOG, "snapshot": SNAPSHOT, "cases": cases}
with open(os.path.join(OUT, "pda.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
print("pda", len(cases))
