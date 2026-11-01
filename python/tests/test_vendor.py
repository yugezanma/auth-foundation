"""tools/vendor.py: 一時の git リポジトリにこのリポジトリを写して確かめる。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VENDOR = os.path.join(ROOT, "tools", "vendor.py")
HAS_NODE = shutil.which("node") is not None


def run(*args, cwd=None):
    return subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)


class VendorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        g = ["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@example.com"]
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
            r = run(*(g + cmd))
            self.assertEqual(r.returncode, 0, r.stderr)
        self.git = g
        with open(os.path.join(self.repo, "VERSION"), encoding="utf-8") as f:
            self.version = f.read().strip()
        self.dest = os.path.join(self.tmp, "app", "vendor")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def vendor(self, lang, *extra):
        return run(sys.executable, VENDOR, "--repo", self.repo, "--lang", lang, "--dest", self.dest, *extra)

    def verify_python(self):
        return run(sys.executable, "-B", "-c",
                   "import sys; sys.path.insert(0, sys.argv[1]); from auth_foundation.verify_vendor import main; sys.exit(main())",
                   self.dest)

    def test_refuses_without_tag(self):
        r = self.vendor("python")
        self.assertEqual(r.returncode, 2)
        self.assertIn("タグ", r.stderr)
        self.assertFalse(os.path.exists(self.dest))

    def test_refuses_when_dirty(self):
        run(*(self.git + ["tag", "v" + self.version]))
        with open(os.path.join(self.repo, "README.md"), "a", encoding="utf-8") as f:
            f.write("x")
        r = self.vendor("python")
        self.assertEqual(r.returncode, 2)
        self.assertIn("未コミット", r.stderr)

    def test_tagged_python(self):
        run(*(self.git + ["tag", "v" + self.version]))
        r = self.vendor("python")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        with open(os.path.join(self.dest, "auth_foundation", "MANIFEST.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual((m["lang"], m["version"], m["tag"], m["dirty"]), ("python", self.version, "v" + self.version, False))
        self.assertIn("evaluate.py", m["files"])
        self.assertIn("vectors/pda.json", m["files"])
        self.assertIn(".gitattributes", m["files"])
        self.assertEqual(self.verify_python().returncode, 0)

    def test_detects_hand_edit_and_refuses_to_overwrite(self):
        self.assertEqual(self.vendor("python", "--allow-dev").returncode, 0)
        target = os.path.join(self.dest, "auth_foundation", "evaluate.py")
        with open(target, "a", encoding="utf-8") as f:
            f.write("# 手で直した\n")
        r = self.verify_python()
        self.assertEqual(r.returncode, 1)
        self.assertIn("手で直さない", r.stdout)
        r = self.vendor("python", "--allow-dev")
        self.assertEqual(r.returncode, 2)
        with open(target, encoding="utf-8") as f:
            self.assertIn("手で直した", f.read())

    def test_detects_extra_file(self):
        self.assertEqual(self.vendor("python", "--allow-dev").returncode, 0)
        with open(os.path.join(self.dest, "auth_foundation", "extra.py"), "w", encoding="utf-8") as f:
            f.write("")
        r = self.verify_python()
        self.assertIn("MANIFEST.json に無いファイル: extra.py", r.stdout)

    def test_replaces_clean_copy(self):
        self.assertEqual(self.vendor("python", "--allow-dev").returncode, 0)
        # キャッシュは確かめの対象外
        os.makedirs(os.path.join(self.dest, "auth_foundation", "__pycache__"), exist_ok=True)
        self.assertEqual(self.vendor("python", "--allow-dev").returncode, 0)

    @unittest.skipUnless(HAS_NODE, "node が無い")
    def test_js(self):
        self.assertEqual(self.vendor("js", "--allow-dev").returncode, 0)
        root = os.path.join(self.dest, "auth_foundation")
        self.assertEqual(sorted(os.listdir(root)),
                         [".gitattributes", "MANIFEST.json", "VERSION", "auth-foundation.mjs", "vectors", "verify-vendor.mjs"])
        r = run("node", os.path.join(root, "verify-vendor.mjs"))
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(os.path.join(root, "auth-foundation.mjs"), "a", encoding="utf-8") as f:
            f.write("\n")
        r = run("node", os.path.join(root, "verify-vendor.mjs"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("手で直さない", r.stdout)


if __name__ == "__main__":
    unittest.main()
