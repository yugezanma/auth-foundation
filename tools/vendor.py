"""判定の部品を各アプリへ写す(docs/設計.md §6-2)。

    python3 tools/vendor.py --lang python --dest <アプリの中の置き場所>
    python3 tools/vendor.py --lang js     --dest <アプリの中の置き場所>

<置き場所>/auth_foundation/ に、部品・判定テスト・VERSION・MANIFEST.json・確かめ用のコード・.gitattributes(改行を変えない)を置く。

- このリポジトリは、タグ v<VERSION> を checkout した、未コミットの変更の無い状態で実行する。
  開発中の版を試しに写すときだけ --allow-dev を付ける(MANIFEST.json の tag が null になる)
- 置き場所にすでに写しがあれば、置き換える前に MANIFEST.json と一致するかを確かめ、
  手で直されていれば止める(直したいことは、このリポジトリで直して版を上げる)
- 一時フォルダに写して確かめ(ハッシュと全部の判定テスト)を流し、通ったときだけ前の写しと入れ替える。
  通らなければ前の写しはそのまま残る。JS 版の確かめには node が要る
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = "auth_foundation"


def fail(msg, problems=()):
    print("vendor.py: " + msg, file=sys.stderr)
    for p in problems:
        print("  " + p, file=sys.stderr)
    sys.exit(2)


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        fail("git %s に失敗: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


def sources(repo, lang):
    """(写す先の相対パス, 元のファイル) の配列。"""
    out = []
    if lang == "python":
        src = os.path.join(repo, "python", PKG)
        for n in sorted(os.listdir(src)):
            if n.endswith(".py"):
                out.append((n, os.path.join(src, n)))
    else:
        for n in ("auth-foundation.mjs", "verify-vendor.mjs"):
            out.append((n, os.path.join(repo, "js", n)))
    vdir = os.path.join(repo, "spec", "vectors")
    for n in sorted(os.listdir(vdir)):
        if n.endswith(".json"):
            out.append(("vectors/" + n, os.path.join(vdir, n)))
    out.append(("VERSION", os.path.join(repo, "VERSION")))
    return out


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_copy(repo, lang, target, version, tag, commit, dirty):
    files = {}
    for rel, src in sources(repo, lang):
        dst = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        files[rel] = sha256_of(dst)
    # 写しを取り込んだリポジトリで、git が改行を変えないようにする(Windows の autocrlf でハッシュが変わるため)
    with open(os.path.join(target, ".gitattributes"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# auth-foundation の写し。改行を変えない(MANIFEST.json のハッシュが変わるため)\n* -text\n")
    files[".gitattributes"] = sha256_of(os.path.join(target, ".gitattributes"))
    manifest = {"name": "auth-foundation", "lang": lang, "version": version, "tag": tag,
                "commit": commit, "dirty": dirty, "files": files}
    with open(os.path.join(target, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def verify_copy(lang, target):
    """写しの確かめを別のプロセスで流す。通れば True。"""
    if lang == "python":
        cmd = [sys.executable, "-B", "-c",
               "import sys; sys.path.insert(0, sys.argv[1]); from auth_foundation.verify_vendor import main; sys.exit(main())",
               os.path.dirname(target)]
    else:
        cmd = ["node", os.path.join(target, "verify-vendor.mjs")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
    return r.returncode == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="判定の部品を各アプリへ写す")
    ap.add_argument("--lang", choices=("python", "js"), required=True)
    ap.add_argument("--dest", required=True, help="アプリの中の置き場所(この下に auth_foundation/ を作る)")
    ap.add_argument("--allow-dev", action="store_true", help="タグの無い・未コミットの変更がある状態でも写す")
    ap.add_argument("--repo", default=os.path.dirname(HERE), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    repo = os.path.abspath(args.repo)

    sys.path.insert(0, os.path.join(repo, "python"))
    from auth_foundation.verify_vendor import check_manifest  # このリポジトリの版を使う

    with open(os.path.join(repo, "VERSION"), encoding="utf-8") as f:
        version = f.read().strip()
    commit = git(repo, "rev-parse", "HEAD")
    dirty = bool(git(repo, "status", "--porcelain"))
    tags = git(repo, "tag", "--points-at", "HEAD").split()
    tag = "v" + version if "v" + version in tags else None
    if not args.allow_dev:
        if dirty:
            fail("未コミットの変更があります。タグを checkout した状態で実行してください(試しに写すなら --allow-dev)")
        if tag is None:
            fail("HEAD にタグ v%s がありません。タグを checkout した状態で実行してください(試しに写すなら --allow-dev)" % version)

    dest = os.path.abspath(args.dest)
    target = os.path.join(dest, PKG)
    if os.path.exists(target):
        problems = check_manifest(target)
        if problems:
            fail("置き場所の写しが MANIFEST.json と合わないので止めました(手で直されているかもしれません): " + target, problems)
    if args.lang == "js" and shutil.which("node") is None:
        fail("node が無いので、JS 版の写しを確かめられません")

    os.makedirs(dest, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".auth_foundation-", dir=dest)
    try:
        staged = os.path.join(staging, PKG)
        write_copy(repo, args.lang, staged, version, tag, commit, dirty)
        if not verify_copy(args.lang, staged):
            fail("写しの確かめに失敗しました。前の写しはそのまま残しています: " + target)
        if os.path.exists(target):
            shutil.rmtree(target)
        os.replace(staged, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("写しました: %s(%s 版 %s%s)" % (target, args.lang, version, "" if tag else "、開発中"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
