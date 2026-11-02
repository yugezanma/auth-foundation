"""判定テスト(汎用の決まり)を書き出す。正解はすべて手で書いている(部品の実装からは作らない)。

判定テストは JSON が正。直すときはこのスクリプトを直して流し直す: python3 tools/vectors/make_generic.py spec/vectors
"""
import copy, json, os, sys

OUT = sys.argv[1]
NOW = "2026-11-01T09:00:00+09:00"

CAT = {
    "features": {
        "report": ["view", "create", "edit", "approve"],
        "site_master": ["view", "edit"],
        "contract": ["view", "edit"],
        "member": ["view", "create", "edit"],
        "audit": ["view"],
    },
    "roles": [
        {"key": "admin", "rank": 5, "audience": "internal", "perms": {
            "report": ["view", "create", "edit", "approve"], "site_master": ["view", "edit"],
            "contract": ["view", "edit"], "member": ["view", "create", "edit"], "audit": ["view"]}},
        {"key": "manager", "rank": 4, "audience": "internal", "perms": {
            "report": ["view", "create", "edit", "approve"], "site_master": ["view"]}},
        {"key": "worker", "rank": 3, "audience": "internal", "perms": {"report": ["view", "create"]}},
        {"key": "office", "rank": 2, "audience": "internal", "perms": {
            "report": ["view"], "contract": ["view", "edit"]}},
        {"key": "viewer", "rank": 1, "audience": "internal", "perms": {
            "report": ["view"], "site_master": ["view"]}},
    ],
}


def snap(assignments, *, memberships=None, teams=None, now=NOW, sites=None, groups=None):
    return {
        "tenant_id": "t",
        "now": now,
        "sites": sites if sites is not None else [
            {"id": "s1", "groups": ["g1"]}, {"id": "s2", "groups": ["g1", "g2"]},
            {"id": "s3", "groups": ["g2"]}, {"id": "s4", "groups": []}],
        "groups": groups if groups is not None else [{"id": "g1"}, {"id": "g2"}],
        "memberships": memberships if memberships is not None else (
            [{"user_id": "u%d" % i, "status": "active"} for i in range(1, 7)]
            + [{"user_id": "u7", "status": "suspended"}, {"user_id": "u8", "status": "invited"}]),
        "teams": teams if teams is not None else [
            {"id": "t1", "members": ["u2", "u3"]}, {"id": "t2", "members": ["u4"]}],
        "assignments": assignments,
    }


def A(aid, ptype, pid, role, stype, sid=None, excl=None, expires=None, revoked=None):
    return {"id": aid, "principal": {"type": ptype, "id": pid}, "role": role,
            "scope": {"type": stype, "id": sid}, "exclusions": excl or [],
            "expires_at": expires, "revoked_at": revoked,
            "granted_by": "u1", "created_at": "2026-10-01T09:00:00+09:00"}


def X(stype, sid):
    return {"type": stype, "id": sid}


def P(aid, role, stype, sid=None, team=None):
    return {"assignment_id": aid, "via": {"type": "team", "id": team} if team else None,
            "scope": {"type": stype, "id": sid}, "role": role, "direct": team is None}


ORG = {"type": "org"}
def S(sid): return {"type": "site", "id": sid}


def ok(*paths): return {"allowed": True, "reason": None, "paths": list(paths)}
def no(reason): return {"allowed": False, "reason": reason, "paths": []}


def ev(name, user, perm, res, expect=None, error=None, **extra):
    c = {"name": name, "call": "evaluate", "args": {"user_id": user, "permission": perm, "resource": res}}
    c["args"].update(extra)
    if error: c["expect_error"] = error
    else: c["expect"] = expect
    return c


def call(name, fn, args, expect=None, error=None):
    c = {"name": name, "call": fn, "args": args}
    if error: c["expect_error"] = error
    else: c["expect"] = expect
    return c


files = {}

# ---------------- catalog
bad = {
    "features": {"report": ["view", "delete", "view"], "site_master": ["view"]},
    "roles": [
        {"key": "a", "rank": 1, "audience": "internal", "perms": {"report": ["view", "edit"], "ghost": ["view"]}},
        {"key": "a", "rank": "2", "audience": "guest", "perms": {}},
        {"key": "b", "rank": 1.5, "audience": "owner", "perms": {"site_master": ["approve"]}},
        {"key": "c", "rank": True, "audience": "partner", "perms": {}},
    ]}
files["catalog"] = {
    "description": "validate_catalog: 正しいカタログと、誤りの種類・並び順",
    "catalog": CAT,
    "cases": [
        call("正しいカタログは誤りなし", "validate_catalog", {}, []),
        call("member・audit が無い", "validate_catalog",
             {"catalog": {"features": {"report": ["view"]}, "roles": []}},
             [{"code": "missing_required_feature", "feature": "member"},
              {"code": "missing_required_feature", "feature": "audit"}]),
        call("動詞の一覧が配列でない", "validate_catalog", {"catalog": {
            "features": {"report": "view,edit", "member": ["view"], "audit": ["view"]},
            "roles": [{"key": "r", "rank": 1, "audience": "internal", "perms": {"member": "view"}}]}},
             [{"code": "invalid_list", "feature": "report"},
              {"code": "invalid_list", "role": "r", "feature": "member"}]),
        call("整数の値の小数(1.0)は整数とみなす(JS では 1.0 と 1 を見分けられないため)", "validate_catalog", {"catalog": {
            "features": {"member": ["view"], "audit": ["view"]},
            "roles": [{"key": "r", "rank": 1.0, "audience": "internal", "perms": {}}]}}, []),
        call("誤りをまとめて決まった順に返す", "validate_catalog", {"catalog": bad}, [
            {"code": "invalid_action", "feature": "report", "action": "delete"},
            {"code": "duplicate_action", "feature": "report", "action": "view"},
            {"code": "missing_required_feature", "feature": "member"},
            {"code": "missing_required_feature", "feature": "audit"},
            {"code": "unknown_action", "role": "a", "feature": "report", "action": "edit"},
            {"code": "unknown_feature", "role": "a", "feature": "ghost"},
            {"code": "duplicate_role", "role": "a"},
            {"code": "invalid_audience", "role": "a"},
            {"code": "invalid_rank", "role": "a"},
            {"code": "invalid_rank", "role": "b"},
            {"code": "unknown_action", "role": "b", "feature": "site_master", "action": "approve"},
            {"code": "invalid_rank", "role": "c"},
        ]),
    ]}
# report に edit は無い(view・delete・view)ので unknown_action になる

# ---------------- basic
files["basic"] = {
    "description": "直接の割当、org と site の範囲、組織全体の操作には site の割当が届かないこと、入力のエラー",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "admin", "org"),
                      A("a2", "user", "u2", "worker", "site", "s1"),
                      A("a3", "user", "u3", "viewer", "org")]),
    "cases": [
        ev("org の admin は組織全体のユーザー管理ができる", "u1", "member.edit", ORG, ok(P("a1", "admin", "org"))),
        ev("org の割当はどの拠点にも届く", "u1", "report.edit", S("s3"), ok(P("a1", "admin", "org"))),
        ev("site の割当はその拠点に届く", "u2", "report.create", S("s1"), ok(P("a2", "worker", "site", "s1"))),
        ev("site の割当はほかの拠点には届かない", "u2", "report.create", S("s2"), no("out_of_scope")),
        ev("site の割当は組織全体の操作には届かない", "u2", "report.create", ORG, no("out_of_scope")),
        ev("どの割当も持たない権限", "u2", "member.view", ORG, no("no_permission")),
        ev("ロールに無い権限", "u2", "site_master.view", S("s1"), no("no_permission")),
        ev("org の viewer はグループの無い拠点も見られる", "u3", "report.view", S("s4"), ok(P("a3", "viewer", "org"))),
        ev("viewer は編集できない", "u3", "report.edit", S("s1"), no("no_permission")),
        ev("割当の無い有効なユーザー", "u5", "report.view", S("s1"), no("no_permission")),
        ev("カタログに無い動詞", "u1", "report.delete", S("s1"), error="unknown_permission"),
        ev("feature.action の形でない", "u1", "report", S("s1"), error="unknown_permission"),
        ev("カタログに無い機能グループ", "u1", "nothing.view", S("s1"), error="unknown_permission"),
        ev("対象の種類が org・site 以外", "u1", "report.view", {"type": "site_group", "id": "g1"}, error="invalid_resource"),
        ev("site の対象に id が無い", "u1", "report.view", {"type": "site"}, error="invalid_resource"),
        ev("未知の拠点", "u1", "report.view", S("s9"), error="unknown_site"),
    ]}

# ---------------- union
files["union"] = {
    "description": "和集合。rank の低いロールだけが持つ権限も残る(rank は判定に使わない)",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "office", "org"),
                      A("a2", "user", "u1", "worker", "site", "s1"),
                      A("a3", "user", "u2", "manager", "site", "s1"),
                      A("a4", "user", "u2", "worker", "site", "s1")], teams=[]),
    "cases": [
        ev("rank の低い office だけが持つ契約の編集", "u1", "contract.edit", S("s1"), ok(P("a1", "office", "org"))),
        ev("worker の起票", "u1", "report.create", S("s1"), ok(P("a2", "worker", "site", "s1"))),
        ev("両方が持つ閲覧は割当の順に2つの経路", "u1", "report.view", S("s1"),
           ok(P("a1", "office", "org"), P("a2", "worker", "site", "s1"))),
        ev("担当外の拠点では office の閲覧だけ", "u1", "report.view", S("s3"), ok(P("a1", "office", "org"))),
        ev("担当外の拠点の起票", "u1", "report.create", S("s3"), no("out_of_scope")),
        ev("組織全体の契約の編集", "u1", "contract.edit", ORG, ok(P("a1", "office", "org"))),
        ev("同じ拠点の2つのロールが同じ権限を持つ", "u2", "report.create", S("s1"),
           ok(P("a3", "manager", "site", "s1"), P("a4", "worker", "site", "s1"))),
        call("permissions_at で和集合を見る", "permissions_at", {"user_id": "u1", "resource": S("s1")}, {
            "report": {"view": [P("a1", "office", "org"), P("a2", "worker", "site", "s1")],
                       "create": [P("a2", "worker", "site", "s1")]},
            "contract": {"view": [P("a1", "office", "org")], "edit": [P("a1", "office", "org")]}}),
    ]}

# ---------------- teams
files["teams"] = {
    "description": "チーム経由の割当、直接とチームの両方から届く経路の並び、見つからないチーム",
    "catalog": CAT,
    "snapshot": snap([A("a1", "team", "t1", "worker", "site_group", "g1"),
                      A("a2", "user", "u2", "manager", "site", "s2"),
                      A("a3", "team", "t9", "admin", "org"),
                      A("a4", "team", "t2", "viewer", "org")],
                     teams=[{"id": "t1", "members": ["u2", "u3", "u7"]}, {"id": "t2", "members": ["u4"]}]),
    "cases": [
        ev("チーム経由は via にチーム、direct は false", "u3", "report.create", S("s1"),
           ok(P("a1", "worker", "site_group", "g1", team="t1"))),
        ev("チームと直接の両方から届く", "u2", "report.create", S("s2"),
           ok(P("a1", "worker", "site_group", "g1", team="t1"), P("a2", "manager", "site", "s2"))),
        ev("直接の割当だけが持つ承認", "u2", "report.approve", S("s2"), ok(P("a2", "manager", "site", "s2"))),
        ev("承認は担当の拠点だけ", "u2", "report.approve", S("s1"), no("out_of_scope")),
        ev("別のチームの org の viewer", "u4", "report.view", S("s3"), ok(P("a4", "viewer", "org", team="t2"))),
        ev("見つからないチームへの割当は集めない", "u4", "member.edit", ORG, no("no_permission")),
        ev("チームに入っていない人", "u5", "report.view", S("s1"), no("no_permission")),
        ev("チームに入っていても停止中なら断る", "u7", "report.view", S("s1"), no("not_member")),
    ]}

# ---------------- groups
files["groups"] = {
    "description": "グループの範囲。1つの拠点が2つのグループに属する(多対多)",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "worker", "site_group", "g1"),
                      A("a2", "user", "u2", "worker", "site_group", "g2"),
                      A("a3", "user", "u3", "manager", "site_group", "g1"),
                      A("a4", "user", "u3", "manager", "site_group", "g2")], teams=[]),
    "cases": [
        ev("g1 の拠点", "u1", "report.create", S("s1"), ok(P("a1", "worker", "site_group", "g1"))),
        ev("g1 と g2 の両方に属する拠点", "u1", "report.create", S("s2"), ok(P("a1", "worker", "site_group", "g1"))),
        ev("g2 だけの拠点", "u1", "report.create", S("s3"), no("out_of_scope")),
        ev("グループに属さない拠点", "u1", "report.create", S("s4"), no("out_of_scope")),
        ev("g2 から両方に属する拠点", "u2", "report.create", S("s2"), ok(P("a2", "worker", "site_group", "g2"))),
        ev("g2 からは g1 だけの拠点に届かない", "u2", "report.create", S("s1"), no("out_of_scope")),
        ev("両方のグループの割当から届く", "u3", "report.approve", S("s2"),
           ok(P("a3", "manager", "site_group", "g1"), P("a4", "manager", "site_group", "g2"))),
        ev("グループの割当は組織全体には届かない", "u3", "report.approve", ORG, no("out_of_scope")),
        call("sites_with: g1", "sites_with", {"user_id": "u1", "permission": "report.create"}, ["s1", "s2"]),
        call("sites_with: g1 と g2", "sites_with", {"user_id": "u3", "permission": "report.create"}, ["s1", "s2", "s3"]),
    ]}

# ---------------- exclusions
files["exclusions"] = {
    "description": "除外リスト(拠点・グループ)。除外は割当ごとで、ほかの割当からは届く。組織全体の操作には当てない",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "viewer", "org", excl=[X("site_group", "g2")]),
                      A("a2", "user", "u2", "worker", "site_group", "g1", excl=[X("site", "s2")]),
                      A("a3", "user", "u2", "viewer", "site", "s2"),
                      A("a4", "user", "u3", "worker", "org", excl=[X("site", "s1"), X("site_group", "g2")]),
                      A("a5", "user", "u4", "viewer", "org", excl=[X("site", "s4")]),
                      A("a6", "team", "t2", "worker", "site", "s4")]),
    "cases": [
        ev("除外に当たらない拠点", "u1", "report.view", S("s1"), ok(P("a1", "viewer", "org"))),
        ev("g2 にも属する拠点は除外", "u1", "report.view", S("s2"), no("out_of_scope")),
        ev("g2 の拠点は除外", "u1", "report.view", S("s3"), no("out_of_scope")),
        ev("グループの無い拠点", "u1", "report.view", S("s4"), ok(P("a1", "viewer", "org"))),
        ev("組織全体の操作には除外を当てない", "u1", "report.view", ORG, ok(P("a1", "viewer", "org"))),
        ev("グループから拠点を1つ除く", "u2", "report.create", S("s1"), ok(P("a2", "worker", "site_group", "g1"))),
        ev("除いた拠点の起票", "u2", "report.create", S("s2"), no("out_of_scope")),
        ev("除いた拠点もほかの割当から届く", "u2", "report.view", S("s2"), ok(P("a3", "viewer", "site", "s2"))),
        ev("拠点とグループの両方を除く", "u3", "report.create", S("s2"), no("out_of_scope")),
        call("sites_with: 除外を引いた残り", "sites_with", {"user_id": "u3", "permission": "report.create"}, ["s4"]),
        ev("除外した拠点にチームの割当が届く", "u4", "report.view", S("s4"), ok(P("a6", "worker", "site", "s4", team="t2"))),
    ]}

# ---------------- lifetime
LT = snap([A("a1", "user", "u1", "admin", "org", expires="2026-11-01T00:00:00Z"),
           A("a2", "user", "u2", "admin", "org", expires="2026-11-01T00:00:00.000001Z"),
           A("a3", "user", "u3", "admin", "org", revoked="2026-11-01T09:00:00+09:00"),
           A("a4", "user", "u4", "admin", "org", revoked="2026-11-02T00:00:00+09:00"),
           A("a5", "user", "u5", "admin", "org", expires="2026-10-31T23:59:59-01:00"),
           A("a6", "user", "u6", "admin", "org"),
           A("a7", "user", "u1", "worker", "site", "s1")], teams=[])


def lt_with(now=None, **kw):
    s = copy.deepcopy(LT)
    if now is not None: s["now"] = now
    for k, v in kw.items(): s["assignments"][0][k] = v
    return s


files["lifetime"] = {
    "description": "期限と失効。now と同じ時刻は「過ぎた」。時差を引いて比べる。時刻の形の誤り",
    "catalog": CAT,
    "snapshot": LT,
    "cases": [
        ev("期限が now と同じ(時差違いの同じ時刻)は過ぎた", "u1", "member.edit", ORG, no("no_permission")),
        ev("期限が now の1マイクロ秒後は有効", "u2", "member.edit", ORG, ok(P("a2", "admin", "org"))),
        ev("失効が now と同じは失効", "u3", "member.edit", ORG, no("no_permission")),
        ev("失効が未来なら有効", "u4", "member.edit", ORG, ok(P("a4", "admin", "org"))),
        ev("時差 -01:00 の期限は now より後", "u5", "member.edit", ORG, ok(P("a5", "admin", "org"))),
        ev("期限も失効も null は有効", "u6", "member.edit", ORG, ok(P("a6", "admin", "org"))),
        ev("期限切れの割当は断る理由にも数えない", "u1", "report.edit", S("s1"), no("no_permission")),
        ev("生きている割当があれば out_of_scope", "u1", "report.create", S("s2"), no("out_of_scope")),
        ev("now が日付だけ", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01")),
        ev("now に時差が無い", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01T09:00:00")),
        ev("now が24時", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01T24:00:00Z")),
        ev("now の時差が +24:00", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01T09:00:00+24:00")),
        ev("now の小数が7桁", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01T09:00:00.0000001Z")),
        ev("now が60秒", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-11-01T09:00:60Z")),
        ev("うるう年の2月29日は正しい", "u6", "member.edit", ORG, ok(P("a6", "admin", "org")),
           snapshot=lt_with(now="2028-02-29T09:00:00+09:00")),
        ev("うるう年でない2月29日", "u6", "member.edit", ORG, error="invalid_time", snapshot=lt_with(now="2026-02-29T09:00:00Z")),
        ev("集めた割当の期限が2月30日", "u1", "member.edit", ORG, error="invalid_time",
           snapshot=lt_with(expires_at="2026-02-30T00:00:00Z")),
        ev("ほかの人の割当の時刻の誤りは見ない", "u6", "member.edit", ORG, ok(P("a6", "admin", "org")),
           snapshot=lt_with(revoked_at="yesterday")),
    ]}

# ---------------- membership
files["membership"] = {
    "description": "有効な所属が無ければ not_member。停止中・招待中・所属なし。所属の重複はエラー",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u7", "admin", "org"),
                      A("a2", "user", "u8", "admin", "org"),
                      A("a3", "user", "u7", "ghost", "org"),
                      A("a4", "user", "u99", "admin", "org")]),
    "cases": [
        ev("停止中", "u7", "member.edit", ORG, no("not_member")),
        ev("招待中", "u8", "member.edit", ORG, no("not_member")),
        ev("所属が無い", "u99", "report.view", S("s1"), no("not_member")),
        call("停止中の permissions_at は空", "permissions_at", {"user_id": "u7", "resource": S("s1")}, {}),
        call("招待中の sites_with は空", "sites_with", {"user_id": "u8", "permission": "report.view"}, []),
        ev("所属が同じ user_id で2つ", "u2", "report.view", S("s1"), error="duplicate_membership",
           snapshot=snap([], memberships=[{"user_id": "u1", "status": "active"}, {"user_id": "u2", "status": "active"},
                                          {"user_id": "u1", "status": "suspended"}])),
    ]}

# ---------------- reasons
files["reasons"] = {
    "description": "断る理由 out_of_scope と no_permission の見分け",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "worker", "site", "s1"),
                      A("a2", "user", "u2", "worker", "org", excl=[X("site", "s1")]),
                      A("a3", "user", "u3", "viewer", "org")], teams=[]),
    "cases": [
        ev("持っている権限がほかの拠点にだけある", "u1", "report.create", S("s2"), no("out_of_scope")),
        ev("持っている権限が組織全体に届かない", "u1", "report.create", ORG, no("out_of_scope")),
        ev("どの割当にも無い権限", "u1", "report.approve", S("s1"), no("no_permission")),
        ev("除外で届かないのは out_of_scope", "u2", "report.create", S("s1"), no("out_of_scope")),
        ev("閲覧だけのロールで編集", "u3", "report.edit", S("s1"), no("no_permission")),
        ev("組織全体の操作で権限が無い", "u3", "member.view", ORG, no("no_permission")),
    ]}

# ---------------- reserved
cat_res = copy.deepcopy(CAT)
cat_res["roles"].append({"key": "partner_worker", "rank": 0, "audience": "partner", "perms": {"report": ["view", "create"]}})
files["reserved"] = {
    "description": "予約(collaboration の割当、equipment の範囲、audience、is_tenant_admin)は判定に効かない",
    "catalog": cat_res,
    "snapshot": snap([A("a1", "collaboration", "c1", "admin", "org"),
                      A("a2", "user", "u2", "admin", "equipment", "e1"),
                      A("a3", "user", "u3", "worker", "site", "s1"),
                      A("a4", "user", "u3", "manager", "equipment", "e9"),
                      A("a5", "user", "u4", "partner_worker", "site", "s1"),
                      A("a6", "group", "u5", "admin", "org")],
                     memberships=[{"user_id": "u1", "status": "active"}, {"user_id": "u2", "status": "active"},
                                  {"user_id": "u3", "status": "active"}, {"user_id": "u4", "status": "active"},
                                  {"user_id": "u5", "status": "active"},
                                  {"user_id": "u6", "status": "active", "is_tenant_admin": True}], teams=[]),
    "cases": [
        ev("collaboration の割当は集めない", "u1", "member.edit", ORG, no("no_permission")),
        ev("equipment の範囲の割当は落とす(組織全体)", "u2", "member.edit", ORG, no("no_permission")),
        ev("equipment の範囲の割当は落とす(拠点)", "u2", "report.view", S("s1"), no("no_permission")),
        ev("equipment の割当は断る理由にも数えない", "u3", "report.approve", S("s1"), no("no_permission")),
        ev("audience は判定に使わない", "u4", "report.create", S("s1"), ok(P("a5", "partner_worker", "site", "s1"))),
        ev("未知の principal の種類は集めない", "u5", "member.edit", ORG, no("no_permission")),
        ev("is_tenant_admin は判定に使わない", "u6", "member.edit", ORG, no("no_permission")),
    ]}

# ---------------- errors
files["errors"] = {
    "description": "データの不整合はエラー。確かめるのは本人の集めた割当だけ。所属が無ければ割当を確かめる前に断る",
    "catalog": CAT,
    "snapshot": snap([A("a1", "user", "u1", "ghost", "org", expires="2026-01-01T00:00:00Z"),
                      A("a2", "user", "u2", "viewer", "region", "r1"),
                      A("a3", "user", "u3", "viewer", "site", "s9"),
                      A("a4", "user", "u4", "viewer", "site_group", "g9"),
                      A("a5", "user", "u5", "viewer", "org", excl=[X("org", None)]),
                      A("a6", "user", "u6", "viewer", "org", excl=[X("site", "s9")]),
                      A("a7", "user", "u7", "ghost", "org"),
                      A("a8", "user", "u8", "viewer", "org", excl=[X("site_group", "g9")]),
                      A("a9", "user", "u9", "viewer", "equipment", "e999"),
                      A("a10", "user", "u9", "worker", "site", "s1")],
                     memberships=[{"user_id": "u%d" % i, "status": "active"} for i in range(1, 7)]
                     + [{"user_id": "u7", "status": "suspended"}, {"user_id": "u8", "status": "active"},
                        {"user_id": "u9", "status": "active"}, {"user_id": "u10", "status": "active"}], teams=[]),
    "cases": [
        ev("未知のロール(期限切れでも確かめる)", "u1", "report.view", S("s1"), error="unknown_role"),
        ev("未知の範囲の種類", "u2", "report.view", S("s1"), error="invalid_scope"),
        ev("範囲の拠点が無い", "u3", "report.view", S("s1"), error="unknown_site"),
        ev("範囲のグループが無い", "u4", "report.view", S("s1"), error="unknown_group"),
        ev("除外の種類が org", "u5", "report.view", S("s1"), error="invalid_exclusion"),
        ev("除外の拠点が無い", "u6", "report.view", S("s1"), error="unknown_site"),
        ev("除外のグループが無い", "u8", "report.view", S("s1"), error="unknown_group"),
        ev("停止中なら割当を確かめる前に断る", "u7", "report.view", S("s1"), no("not_member")),
        ev("停止中でも permission の誤りはエラー", "u7", "report.delete", S("s1"), error="unknown_permission"),
        ev("equipment の ID は確かめない", "u9", "report.create", S("s1"), ok(P("a10", "worker", "site", "s1"))),
        ev("ほかの人の割当の誤りは見ない", "u10", "report.view", S("s1"), no("no_permission")),
        ev("拠点の ID が重複", "u10", "report.view", S("s1"), error="duplicate_site",
           snapshot=snap([], sites=[{"id": "s1", "groups": []}, {"id": "s1", "groups": []}])),
        ev("ロールの動詞の一覧が文字列なら何も許さない(部分一致しない)", "u10", "report.create", S("s1"), no("no_permission"),
           catalog={"features": CAT["features"], "roles": [{"key": "w", "rank": 1, "audience": "internal", "perms": {"report": "view,create"}}]},
           snapshot=snap([A("x1", "user", "u10", "w", "org")], memberships=[{"user_id": "u10", "status": "active"}])),
        ev("カタログの動詞の一覧が文字列なら、その権限は未知", "u10", "report.view", S("s1"), error="unknown_permission",
           catalog={"features": {"report": "view", "member": ["view"], "audit": ["view"]}, "roles": []}),
        ev("チームのメンバーが文字列なら誰も入っていない", "u1", "report.view", S("s1"), no("no_permission"),
           snapshot=snap([A("x1", "team", "tt", "viewer", "org")], memberships=[{"user_id": "u1", "status": "active"}],
                         teams=[{"id": "tt", "members": "u1u2"}])),
        ev("拠点のグループが文字列ならどのグループにも属さない", "u1", "report.view", S("s1"), no("out_of_scope"),
           snapshot=snap([A("x1", "user", "u1", "viewer", "site_group", "g1")], memberships=[{"user_id": "u1", "status": "active"}],
                         sites=[{"id": "s1", "groups": "g1"}])),
        call("permissions_at も同じエラー", "permissions_at", {"user_id": "u1", "resource": S("s1")}, error="unknown_role"),
        call("permissions_at の未知の拠点", "permissions_at", {"user_id": "u10", "resource": S("s9")}, error="unknown_site"),
        call("sites_with の未知の権限", "sites_with", {"user_id": "u10", "permission": "x.view"}, error="unknown_permission"),
    ]}

# ---------------- helpers
files["helpers"] = {
    "description": "permissions_at と sites_with",
    "catalog": CAT,
    "snapshot": snap([A("a1", "team", "t1", "worker", "site_group", "g1"),
                      A("a2", "user", "u2", "manager", "site", "s2"),
                      A("a3", "user", "u2", "viewer", "org", excl=[X("site", "s4")])]),
    "cases": [
        call("チーム・直接・org がそろう拠点", "permissions_at", {"user_id": "u2", "resource": S("s2")}, {
            "report": {"view": [P("a1", "worker", "site_group", "g1", team="t1"), P("a2", "manager", "site", "s2"), P("a3", "viewer", "org")],
                       "create": [P("a1", "worker", "site_group", "g1", team="t1"), P("a2", "manager", "site", "s2")],
                       "edit": [P("a2", "manager", "site", "s2")],
                       "approve": [P("a2", "manager", "site", "s2")]},
            "site_master": {"view": [P("a2", "manager", "site", "s2"), P("a3", "viewer", "org")]}}),
        call("どの割当も届かない拠点は空", "permissions_at", {"user_id": "u2", "resource": S("s4")}, {}),
        call("組織全体には org の割当だけ", "permissions_at", {"user_id": "u2", "resource": ORG}, {
            "report": {"view": [P("a3", "viewer", "org")]}, "site_master": {"view": [P("a3", "viewer", "org")]}}),
        call("チームだけ", "permissions_at", {"user_id": "u3", "resource": S("s1")}, {
            "report": {"view": [P("a1", "worker", "site_group", "g1", team="t1")],
                       "create": [P("a1", "worker", "site_group", "g1", team="t1")]}}),
        call("閲覧できる拠点(除外を引く)", "sites_with", {"user_id": "u2", "permission": "report.view"}, ["s1", "s2", "s3"]),
        call("承認できる拠点", "sites_with", {"user_id": "u2", "permission": "report.approve"}, ["s2"]),
        call("チームで起票できる拠点", "sites_with", {"user_id": "u3", "permission": "report.create"}, ["s1", "s2"]),
        call("割当の無い人", "sites_with", {"user_id": "u5", "permission": "report.view"}, []),
        call("停止中の人", "sites_with", {"user_id": "u7", "permission": "report.view"}, []),
    ]}

# ---------------- guard
def g(assignments, memberships=None, teams=None):
    return snap(assignments, memberships=memberships or [
        {"user_id": "u1", "status": "active"}, {"user_id": "u2", "status": "active"}, {"user_id": "u3", "status": "active"}],
        teams=teams or [])


B = g([A("a1", "user", "u1", "admin", "org"), A("a2", "user", "u2", "admin", "org"), A("a3", "user", "u3", "viewer", "org")])


def gc(name, before, after, actor, expect=None, error=None, perm=None):
    args = {"before": before, "after": after, "actor_user_id": actor}
    if perm: args["guard_permission"] = perm
    return call(name, "check_guard", args, expect, error)


files["guard"] = {
    "description": "check_guard: 最後の管理者を守る(no_admin_left)、自分を締め出さない(self_lockout)",
    "catalog": CAT,
    "cases": [
        gc("ほかの管理者を降格(管理者は残る)", B, g([A("a1", "user", "u1", "admin", "org"), A("a3", "user", "u3", "viewer", "org")]), "u1", []),
        gc("自分を降格", B, g([A("a2", "user", "u2", "admin", "org"), A("a3", "user", "u3", "viewer", "org")]), "u1",
           [{"code": "self_lockout"}]),
        gc("管理者が全員いなくなる", B, g([A("a3", "user", "u3", "viewer", "org")]), "u1",
           [{"code": "no_admin_left"}, {"code": "self_lockout"}]),
        gc("管理者でない人が管理者を全員外す", B, g([A("a3", "user", "u3", "viewer", "org")]), "u3", [{"code": "no_admin_left"}]),
        gc("ほかの管理者を停止", B, g(B["assignments"], memberships=[
            {"user_id": "u1", "status": "active"}, {"user_id": "u2", "status": "suspended"}, {"user_id": "u3", "status": "active"}]), "u1", []),
        gc("自分を停止", B, g(B["assignments"], memberships=[
            {"user_id": "u1", "status": "suspended"}, {"user_id": "u2", "status": "active"}, {"user_id": "u3", "status": "active"}]), "u1",
           [{"code": "self_lockout"}]),
        gc("チーム経由の管理者がチームを抜ける",
           g([A("a1", "team", "t1", "admin", "org"), A("a2", "user", "u2", "admin", "org")], teams=[{"id": "t1", "members": ["u1"]}]),
           g([A("a1", "team", "t1", "admin", "org"), A("a2", "user", "u2", "admin", "org")], teams=[{"id": "t1", "members": []}]),
           "u1", [{"code": "self_lockout"}]),
        gc("拠点だけの admin は守る権限に数えない", B,
           g([A("a1", "user", "u1", "admin", "site", "s1"), A("a3", "user", "u3", "viewer", "org")]), "u1",
           [{"code": "no_admin_left"}, {"code": "self_lockout"}]),
        gc("期限切れの admin は守る権限に数えない", B,
           g([A("a1", "user", "u1", "admin", "org"), A("a2", "user", "u2", "admin", "org", expires="2026-11-01T09:00:00+09:00")]), "u2",
           [{"code": "self_lockout"}]),
        gc("守る権限を指定する", g([A("a1", "user", "u1", "office", "org"), A("a2", "user", "u2", "viewer", "org")]),
           g([A("a1", "user", "u1", "viewer", "org"), A("a2", "user", "u2", "viewer", "org")]), "u1",
           [{"code": "no_admin_left"}, {"code": "self_lockout"}], perm="contract.edit"),
        gc("変更の後に未知のロール", B, g([A("a1", "user", "u1", "ghost", "org")]), "u1", error="unknown_role"),
        gc("未知の守る権限", B, B, "u1", error="unknown_permission", perm="member.delete"),
    ]}

# ---------------- tenants
# テナントごとのスナップショット(設計.md §3-3)。X と Y に同じ ID の拠点 A がある。op1 は運営側の人で、どちらにも所属しない
def tsnap(tid, sites, memberships, assignments):
    return {"tenant_id": tid, "now": NOW, "sites": [{"id": s, "groups": []} for s in sites], "groups": [],
            "memberships": [{"user_id": u, "status": "active"} for u in memberships], "teams": [],
            "assignments": assignments}


TX = tsnap("x", ["A", "B"], ["xa", "xc"], [A("ax1", "user", "xa", "admin", "org"), A("ax2", "user", "xc", "worker", "site", "A")])
TY = tsnap("y", ["A", "C"], ["ya", "yv"], [A("ay1", "user", "ya", "admin", "org"), A("ay2", "user", "yv", "viewer", "org")])
TY_NO_ADMIN = tsnap("y", ["A", "C"], ["ya", "yv"], [A("ay2", "user", "yv", "viewer", "org")])
TY_MIXED = tsnap("y", ["A", "C"], ["ya", "yv"], TY["assignments"] + [A("ax9", "user", "ya", "worker", "site", "B")])

files["tenants"] = {
    "description": "テナントが分かれていること。部品はスナップショット(1つのテナントのデータ)の中だけを見るので、ほかのテナントの人は not_member、"
                   "同じ ID の拠点も混ざらず、check_guard もテナントごとになる。op1 は運営側の人で、お客様のテナントに所属しない(設計.md §3-8)",
    "catalog": CAT,
    "snapshot": TX,
    "cases": [
        ev("X の管理者は X の拠点 A を操作できる", "xa", "report.edit", S("A"), ok(P("ax1", "admin", "org"))),
        ev("X の作成者は X の拠点 A で起票できる", "xc", "report.create", S("A"), ok(P("ax2", "worker", "site", "A"))),
        ev("Y の人を X のスナップショットで判定すると not_member", "yv", "report.view", S("A"), no("not_member")),
        ev("運営側の人はお客様のテナントに所属しないので not_member", "op1", "report.view", S("A"), no("not_member")),
        ev("X の管理者を Y のスナップショットで判定すると not_member", "xa", "report.view", S("A"), no("not_member"),
           snapshot=TY),
        ev("Y の閲覧者は Y の拠点 A を見られる(X の拠点 A とは別)", "yv", "report.view", S("A"),
           ok(P("ay2", "viewer", "org")), snapshot=TY),
        ev("Y に無い拠点(X にだけある B)は Y ではエラー", "ya", "report.view", S("B"), error="unknown_site", snapshot=TY),
        ev("ほかのテナントの割当が混ざり、Y に無い拠点を指していればエラー", "ya", "report.view", S("A"),
           error="unknown_site", snapshot=TY_MIXED),
        call("X の作成者が起票できる拠点(X の中)", "sites_with", {"user_id": "xc", "permission": "report.create"}, ["A"]),
        call("X の作成者を Y で数えると0件", "sites_with",
             {"user_id": "xc", "permission": "report.create", "snapshot": TY}, []),
        call("Y の管理者が見られる拠点(Y の中だけ)", "sites_with",
             {"user_id": "ya", "permission": "report.view", "snapshot": TY}, ["A", "C"]),
        call("X の管理者の Y での権限は空", "permissions_at", {"user_id": "xa", "resource": ORG, "snapshot": TY}, {}),
        call("X に管理者がいても、Y の最後の管理者が自分を外せば Y で違反", "check_guard",
             {"before": TY, "after": TY_NO_ADMIN, "actor_user_id": "ya"}, [{"code": "no_admin_left"}, {"code": "self_lockout"}]),
        call("運営側の人が Y の最後の管理者を外すと no_admin_left(運営側は数に入らない)", "check_guard",
             {"before": TY, "after": TY_NO_ADMIN, "actor_user_id": "op1"}, [{"code": "no_admin_left"}]),
        call("X の管理者が Y の変更をしても、X の管理者は Y の数に入らない", "check_guard",
             {"before": TY, "after": TY, "actor_user_id": "xa"}, []),
    ]}

# ---------------- audit
EV_MIN = {"host_tenant_id": "t", "actor_user_id": "u1", "action": "member.created",
          "target_type": "user", "target_id": "u2", "created_at": "2026-11-01T09:00:00+09:00"}
EV_FULL = {"id": "e1", "host_tenant_id": "t", "actor_user_id": "u1", "actor_tenant_id": "t", "action": "member.updated",
           "target_type": "user", "target_id": "u2", "before": {"name": "A"}, "after": {"name": "B"},
           "ip_address": "127.0.0.1", "created_at": "2026-11-01T09:00:00Z"}


def ve(name, event, expect):
    return call(name, "validate_audit_event", {"event": event}, expect)


def withv(base, **kw):
    e = copy.deepcopy(base)
    for k, v in kw.items():
        if v is DEL: e.pop(k, None)
        else: e[k] = v
    return e


DEL = object()
files["audit"] = {
    "description": "監査ログの形(make_audit_event・validate_audit_event・audit_retention)",
    "cases": [
        call("足りない任意の項目は null、actor_tenant_id は host と同じ", "make_audit_event", {"fields": EV_MIN}, {
            "id": None, "host_tenant_id": "t", "actor_user_id": "u1", "actor_tenant_id": "t", "action": "member.created",
            "target_type": "user", "target_id": "u2", "before": None, "after": None, "ip_address": None,
            "created_at": "2026-11-01T09:00:00+09:00"}),
        call("全部の項目があればそのまま", "make_audit_event", {"fields": EV_FULL}, EV_FULL),
        call("秘密のキーがあれば作らない", "make_audit_event", {"fields": withv(EV_MIN, after={"password": "x"})},
             error="invalid_audit_event"),
        call("表に無い項目があれば作らない", "make_audit_event", {"fields": withv(EV_MIN, extra=1)}, error="invalid_audit_event"),
        call("必須の項目が無ければ作らない", "make_audit_event", {"fields": withv(EV_MIN, action=DEL)}, error="invalid_audit_event"),
        ve("正しい記録", EV_FULL, []),
        ve("任意の項目は無くてよい", EV_MIN | {"actor_tenant_id": "t"}, []),
        ve("id は整数でもよい", withv(EV_FULL, id=12), []),
        ve("整数の値の小数(2.0)は整数とみなす", withv(EV_FULL, id=2.0), []),
        ve("登録の無いメールアドレスのログイン失敗", {
            "host_tenant_id": "t", "actor_user_id": None, "actor_tenant_id": "t", "action": "auth.login.failed",
            "target_type": "email", "target_id": "nobody@example.com", "after": {"reason": "wrong_password"},
            "created_at": "2026-11-01T09:00:00+09:00"}, []),
        ve("必須の項目が無い・null", withv(EV_FULL, host_tenant_id=DEL, created_at=None), [
            {"code": "missing_field", "field": "host_tenant_id"}, {"code": "missing_field", "field": "created_at"}]),
        ve("型の誤り", withv(EV_FULL, id=1.5, actor_user_id=123, target_id="", before=["x"], after="y", ip_address=1), [
            {"code": "invalid_type", "field": "id"}, {"code": "invalid_type", "field": "actor_user_id"},
            {"code": "invalid_type", "field": "target_id"}, {"code": "invalid_type", "field": "before"},
            {"code": "invalid_type", "field": "after"}, {"code": "invalid_type", "field": "ip_address"}]),
        ve("時刻の形でない", withv(EV_FULL, created_at="2026-11-01 09:00"), [{"code": "invalid_time", "field": "created_at"}]),
        ve("未知の操作名", withv(EV_FULL, action="member.deleted"), [{"code": "unknown_action", "field": "action"}]),
        ve("大文字の操作名", withv(EV_FULL, action="App.upload"), [{"code": "unknown_action", "field": "action"}]),
        ve("業務の記録 app.*", withv(EV_FULL, action="app.upload.created"), []),
        ve("拠点の追加", withv(EV_FULL, action="site.created", target_type="site"), []),
        ve("拠点以外のアーカイブ", withv(EV_FULL, action="equipment.archived"), []),
        ve("予約の操作名", withv(EV_FULL, action="report.published"), []),
        ve("秘密のキー(入れ子・配列・code)と、表に無い項目", withv(
            EV_FULL, before={"session_id": "s", "name": "A"},
            after={"user": {"password_hash": "h", "Site_Id": "A"}, "items": [{"ok": 1}, {"Token": "t"}], "code": "123456"},
            extra="x", note=None), [
            {"code": "secret_field", "field": "before.session_id"},
            {"code": "secret_field", "field": "after.user.password_hash"},
            {"code": "secret_field", "field": "after.items.1.Token"},
            {"code": "secret_field", "field": "after.code"},
            {"code": "unknown_field", "field": "extra"},
            {"code": "unknown_field", "field": "note"}]),
        ve("単語に分けて見る(_・-・大文字の境目)。単語の頭が秘密の語なら秘密", withv(EV_FULL, after={
            "otp_sent": True, "client_secret": "x", "old_passwd": "y", "verification_code": "1", "passwordHash": "h",
            "access-tokens": ["t"], "new_pwd": "p", "SessionID": "s", "site_code": "A"}), [
            {"code": "secret_field", "field": "after.otp_sent"},
            {"code": "secret_field", "field": "after.client_secret"},
            {"code": "secret_field", "field": "after.old_passwd"},
            {"code": "secret_field", "field": "after.verification_code"},
            {"code": "secret_field", "field": "after.passwordHash"},
            {"code": "secret_field", "field": "after.access-tokens"},
            {"code": "secret_field", "field": "after.new_pwd"},
            {"code": "secret_field", "field": "after.SessionID"},
            {"code": "secret_field", "field": "after.site_code"}]),
        ve("秘密の語を単語の途中に含むだけなら秘密でない", withv(EV_FULL, after={
            "footprint_kwh": 1, "hotplate": 2, "barcode": "x", "tokenless": None, "unsecret": 1}), []),
        call("運営側の操作は actor_tenant_id を operator にしたまま作る", "make_audit_event", {"fields": {
            "host_tenant_id": "t2", "actor_user_id": "op1", "actor_tenant_id": "ops", "action": "tenant.created",
            "target_type": "tenant", "target_id": "t2", "after": {"name": "B社"}, "created_at": "2026-11-02T09:00:00+09:00"}}, {
            "id": None, "host_tenant_id": "t2", "actor_user_id": "op1", "actor_tenant_id": "ops", "action": "tenant.created",
            "target_type": "tenant", "target_id": "t2", "before": None, "after": {"name": "B社"}, "ip_address": None,
            "created_at": "2026-11-02T09:00:00+09:00"}),
        ve("運営側がテナントを止める", withv(EV_FULL, actor_user_id="op1", actor_tenant_id="ops", action="tenant.suspended",
                                     target_type="tenant", target_id="t", before={"status": "active"},
                                     after={"status": "suspended"}), []),
        ve("お客様の管理者がサポートの閲覧を許可する", withv(EV_FULL, action="support_access.granted", target_type="support_grant",
                                             target_id="g1", before=None,
                                             after={"expires_at": "2026-11-09T09:00:00+09:00"}), []),
        ve("運営側がサポートの閲覧を始める", withv(EV_FULL, actor_user_id="op1", actor_tenant_id="ops",
                                        action="support_access.started", target_type="support_grant", target_id="g1",
                                        before=None, after=None), []),
        ve("テナントの分からないログインの失敗は operator テナントに記録する", {
            "host_tenant_id": "ops", "actor_user_id": None, "actor_tenant_id": "ops", "action": "auth.login.failed",
            "target_type": "email", "target_id": "nobody@example.com", "after": {"reason": "unknown_email"},
            "created_at": "2026-11-02T09:00:00+09:00"}, []),
        call("ログインの記録は13か月", "audit_retention", {"action": "auth.login.failed"}, "13_months"),
        call("ユーザー管理は無期限", "audit_retention", {"action": "member.created"}, "indefinite"),
        call("拠点の追加は無期限", "audit_retention", {"action": "site.created"}, "indefinite"),
        call("拠点以外のアーカイブは無期限", "audit_retention", {"action": "equipment.unarchived"}, "indefinite"),
        call("テナントの停止は無期限", "audit_retention", {"action": "tenant.suspended"}, "indefinite"),
        call("サポートの閲覧は無期限", "audit_retention", {"action": "support_access.started"}, "indefinite"),
        call("業務の記録は13か月", "audit_retention", {"action": "app.pdf.exported"}, "13_months"),
        call("予約の操作名", "audit_retention", {"action": "report.published"}, "indefinite"),
        call("未知の操作名", "audit_retention", {"action": "member.deleted"}, error="unknown_action"),
    ]}

os.makedirs(OUT, exist_ok=True)
for name, body in files.items():
    doc = {"name": name, **body}
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(name, len(body["cases"]))
