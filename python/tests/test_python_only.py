"""判定テストに書けない、Python 版だけの扱い。"""
import os
import sys
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "python"))

import auth_foundation as af  # noqa: E402

CAT = {"features": {"report": ["view", "edit"], "member": ["view", "edit"], "audit": ["view"]},
       "roles": [{"key": "admin", "rank": 2, "audience": "internal",
                  "perms": {"report": ["view", "edit"], "member": ["view", "edit"], "audit": ["view"]}},
                 {"key": "worker", "rank": 1, "audience": "internal", "perms": {"report": ["view", "edit"]}}]}


class ErrorTest(unittest.TestCase):
    def test_error_has_code_and_is_exception(self):
        with self.assertRaises(af.AuthFoundationError) as cm:
            af.evaluate(CAT, {"now": "2026-11-01T00:00:00Z"}, "u1", "report.view", {"type": "site", "id": "x"})
        self.assertEqual(cm.exception.code, "unknown_site")
        self.assertIsInstance(cm.exception, Exception)

    def test_resource_not_a_dict(self):
        for r in (None, "org", ["org"], {"type": "site", "id": 3}, {"type": "site", "id": ""}):
            with self.subTest(r=r), self.assertRaises(af.AuthFoundationError) as cm:
                af.evaluate(CAT, {"now": "2026-11-01T00:00:00Z"}, "u1", "report.view", r)
            self.assertEqual(cm.exception.code, "invalid_resource")

    def test_permission_not_a_string(self):
        with self.assertRaises(af.AuthFoundationError) as cm:
            af.evaluate(CAT, {}, "u1", None, {"type": "org"})
        self.assertEqual(cm.exception.code, "unknown_permission")

    def test_audit_event_not_a_dict(self):
        self.assertEqual(af.validate_audit_event([]), [{"code": "invalid_type", "field": "event"}])
        with self.assertRaises(af.AuthFoundationError) as cm:
            af.make_audit_event(None)
        self.assertEqual(cm.exception.code, "invalid_audit_event")

    def test_make_audit_event_reports_errors(self):
        with self.assertRaises(af.AuthFoundationError) as cm:
            af.make_audit_event({"host_tenant_id": "t", "action": "member.created", "target_type": "user",
                                 "target_id": "u", "created_at": "2026-11-01T00:00:00Z", "after": {"token": "x"}})
        self.assertEqual(cm.exception.detail, [{"code": "secret_field", "field": "after.token"}])

    def test_does_not_modify_inputs(self):
        import copy
        snap = {"now": "2026-11-01T00:00:00Z", "sites": [{"id": "s1", "groups": []}], "groups": [],
                "memberships": [{"user_id": "u1", "status": "active"}], "teams": [],
                "assignments": [{"id": "a1", "principal": {"type": "user", "id": "u1"}, "role": "admin",
                                 "scope": {"type": "org", "id": "t"}, "exclusions": []}]}
        before = copy.deepcopy(snap)
        r = af.evaluate(CAT, snap, "u1", "report.edit", {"type": "site", "id": "s1"})
        r["paths"][0]["scope"]["type"] = "changed"
        self.assertEqual(snap, before)
        self.assertEqual(r["paths"][0]["assignment_id"], "a1")


class ScaleTest(unittest.TestCase):
    """設計.md §2 の将来の上限(300名・3,000拠点)で、使える速さで動くこと。"""

    def test_sites_with_3000_sites(self):
        sites = [{"id": "s%04d" % i, "groups": ["g%d" % (i % 8)]} for i in range(3000)]
        groups = [{"id": "g%d" % i} for i in range(8)]
        members = [{"user_id": "u%03d" % i, "status": "active"} for i in range(300)]
        teams = [{"id": "t%d" % i, "members": ["u%03d" % j for j in range(i * 10, i * 10 + 10)]} for i in range(30)]
        assigns = [{"id": "a%d" % i, "principal": {"type": "team", "id": "t%d" % i}, "role": "worker",
                    "scope": {"type": "site_group", "id": "g%d" % (i % 8)}, "exclusions": []} for i in range(30)]
        assigns += [{"id": "d%d" % i, "principal": {"type": "user", "id": "u%03d" % (i % 300)}, "role": "worker",
                     "scope": {"type": "site", "id": "s%04d" % i}, "exclusions": []} for i in range(3000)]
        snap = {"now": "2026-11-01T00:00:00Z", "sites": sites, "groups": groups, "memberships": members,
                "teams": teams, "assignments": assigns}
        t = time.perf_counter()
        got = af.sites_with(CAT, snap, "u000", "report.edit")
        self.assertLess(time.perf_counter() - t, 2.0)
        self.assertEqual(len(got), 375 + 10 - sum(1 for i in range(0, 3000, 300) if i % 8 == 0))


if __name__ == "__main__":
    unittest.main()
