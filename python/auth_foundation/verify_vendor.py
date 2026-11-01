"""判定テストを流す仕組みと、写し(vendoring)の確かめ。

各アプリのテストからは次のように呼ぶ(写した場所を sys.path に入れておく):

    from auth_foundation.verify_vendor import verify
    verify()   # 写しが手で直されていないか(MANIFEST.json)と、全部の判定テストを確かめる。だめなら VendorCheckError

コマンドからは ``python -m auth_foundation.verify_vendor``。
"""
import hashlib
import json
import os
import sys

from . import (AuthFoundationError, __version__, audit_retention, check_guard, evaluate, make_audit_event,
               permissions_at, sites_with, validate_audit_event, validate_catalog)

HERE = os.path.dirname(os.path.abspath(__file__))
IGNORED_DIRS = ("__pycache__",)
IGNORED_SUFFIXES = (".pyc",)
IGNORED_NAMES = (".DS_Store", "Thumbs.db", "desktop.ini")  # OS が勝手に作るファイル(JS 版と同じ)


class VendorCheckError(Exception):
    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


def _same(a, b):
    """JSON として同じか(bool と数を区別し、配列は順番まで、オブジェクトはキーの順を問わない)。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _invoke(doc, case):
    args = case.get("args", {})
    cat = args.get("catalog", doc.get("catalog"))
    snap = args.get("snapshot", doc.get("snapshot"))
    c = case["call"]
    if c == "validate_catalog":
        return validate_catalog(cat)
    if c == "evaluate":
        return evaluate(cat, snap, args["user_id"], args["permission"], args["resource"])
    if c == "permissions_at":
        return permissions_at(cat, snap, args["user_id"], args["resource"])
    if c == "sites_with":
        return sites_with(cat, snap, args["user_id"], args["permission"])
    if c == "check_guard":
        return check_guard(cat, args["before"], args["after"], args["actor_user_id"],
                           args.get("guard_permission", "member.edit"))
    if c == "make_audit_event":
        return make_audit_event(args["fields"])
    if c == "validate_audit_event":
        return validate_audit_event(args["event"])
    if c == "audit_retention":
        return audit_retention(args["action"])
    raise ValueError("未知の call: %s" % c)


def run_case(doc, case):
    """1件を流す。合えば None、合わなければ理由の文字列。"""
    try:
        got = _invoke(doc, case)
    except AuthFoundationError as e:
        if "expect_error" in case:
            return None if e.code == case["expect_error"] else "エラー %s(正解は %s)" % (e.code, case["expect_error"])
        return "エラー %s(正解は戻り値)" % e.code
    if "expect_error" in case:
        return "戻り値 %s(正解はエラー %s)" % (json.dumps(got, ensure_ascii=False), case["expect_error"])
    if not _same(got, case["expect"]):
        return "戻り値 %s\n    正解 %s" % (json.dumps(got, ensure_ascii=False), json.dumps(case["expect"], ensure_ascii=False))
    return None


def run_vectors(vectors_dir):
    """vectors_dir の判定テストをすべて流す。(通った件数, 失敗の配列) を返す。"""
    passed, failures = 0, []
    names = sorted(n for n in os.listdir(vectors_dir) if n.endswith(".json"))
    if not names:
        failures.append("判定テストが1つもありません: %s" % vectors_dir)
    for n in names:
        with open(os.path.join(vectors_dir, n), encoding="utf-8") as f:
            doc = json.load(f)
        for case in doc["cases"]:
            why = run_case(doc, case)
            if why is None:
                passed += 1
            else:
                failures.append("%s / %s: %s" % (n, case.get("name"), why))
    return passed, failures


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(root):
    """写しの中のファイル(root からの相対パス、/ 区切り)。キャッシュは除く。"""
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in IGNORED_DIRS)
        for n in sorted(files):
            if n.endswith(IGNORED_SUFFIXES) or n in IGNORED_NAMES:
                continue
            out.append(os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/"))
    return out


def check_manifest(root):
    """MANIFEST.json と中身が一致するか。問題の配列を返す。"""
    mpath = os.path.join(root, "MANIFEST.json")
    if not os.path.exists(mpath):
        return ["MANIFEST.json がありません: %s" % root]
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    problems = []
    listed = manifest.get("files", {})
    for rel in list_files(root):
        if rel == "MANIFEST.json":
            continue
        if rel not in listed:
            problems.append("MANIFEST.json に無いファイル: %s" % rel)
        elif sha256_of(os.path.join(root, rel)) != listed[rel]:
            problems.append("写したときと中身が違う(手で直さない): %s" % rel)
    for rel in listed:
        if not os.path.exists(os.path.join(root, rel)):
            problems.append("写したファイルが無い: %s" % rel)
    return problems


def verify(root=None):
    """写しを確かめる。問題があれば VendorCheckError。通った判定テストの件数を返す。"""
    root = root or HERE
    problems = check_manifest(root)
    vpath = os.path.join(root, "VERSION")
    if os.path.exists(vpath):
        with open(vpath, encoding="utf-8") as f:
            v = f.read().strip()
        if v != __version__:
            problems.append("VERSION(%s)と部品の版(%s)が違う" % (v, __version__))
    passed, failures = run_vectors(os.path.join(root, "vectors"))
    problems += failures
    if problems:
        raise VendorCheckError(problems)
    return passed


def main():
    try:
        n = verify()
    except VendorCheckError as e:
        print("auth_foundation %s: 写しの確かめに失敗" % __version__)
        for p in e.problems:
            print("  " + p)
        return 1
    print("auth_foundation %s: 写しは正しく、判定テスト %d 件が通った" % (__version__, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
