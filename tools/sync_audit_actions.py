"""spec/audit-actions.json の操作名の一覧を、Python 版と JS 版の部品に書き込む。

    python3 tools/sync_audit_actions.py          # 書き込む
    python3 tools/sync_audit_actions.py --check  # 書き込まずに、今の部品と一致するかだけを見る(違えば 1)

部品の中の「>>> ここから下は」の行から「<<< ここまで」の行までを書き直す。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "audit-actions.json")
BEGIN = ">>> ここから下は tools/sync_audit_actions.py が spec/audit-actions.json から書く(手で直さない)"
END = "<<< ここまで"


def py_block(d):
    acts = "\n".join("    (%r, %r, %r, %r)," % (a["name"], a["required"], a["retention"], a["reserved"]) for a in d["actions"])
    pats = "\n".join("    (%r, %r, %r)," % (p["pattern"], p["required"], p["retention"]) for p in d["patterns"])
    return ("# spec/audit-actions.json と同じ一覧(テストで突き合わせる)。(名前, 必須か, 保存期間, 予約か)\n"
            "ACTIONS = (\n%s\n)\n"
            "# (正規表現, 必須か, 保存期間)。ACTIONS に無い名前に、上から順に当てる\n"
            "PATTERNS = (\n%s\n)\n" % (acts, pats))


def js_block(d):
    j = json.dumps
    acts = ",\n".join("  [%s, %s, %s, %s]" % (j(a["name"]), j(a["required"]), j(a["retention"]), j(a["reserved"])) for a in d["actions"])
    pats = ",\n".join("  [%s, %s, %s]" % (j(p["pattern"]), j(p["required"]), j(p["retention"])) for p in d["patterns"])
    return ("// spec/audit-actions.json と同じ一覧(テストで突き合わせる)。[名前, 必須か, 保存期間, 予約か]\n"
            "export const AUDIT_ACTIONS = [\n%s\n];\n"
            "// [正規表現, 必須か, 保存期間]。AUDIT_ACTIONS に無い名前に、上から順に当てる\n"
            "export const AUDIT_PATTERNS = [\n%s\n];\n" % (acts, pats))


TARGETS = [(os.path.join(ROOT, "python", "auth_foundation", "audit.py"), "# ", py_block),
           (os.path.join(ROOT, "js", "auth-foundation.mjs"), "// ", js_block)]


def rewrite(text, comment, block):
    b, e = comment + BEGIN, comment + END
    i, j = text.index(b) + len(b) + 1, text.index(e)
    return text[:i] + block + text[j:]


def main(argv):
    check = "--check" in argv
    with open(SPEC, encoding="utf-8") as f:
        d = json.load(f)
    stale = []
    for path, comment, make in TARGETS:
        with open(path, encoding="utf-8") as f:
            old = f.read()
        new = rewrite(old, comment, make(d))
        if new != old:
            stale.append(os.path.relpath(path, ROOT))
            if not check:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
    if check and stale:
        print("spec/audit-actions.json と違う: " + ", ".join(stale) + "(python3 tools/sync_audit_actions.py で直す)")
        return 1
    if not check:
        print("書き直した: " + (", ".join(stale) if stale else "(変更なし)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
