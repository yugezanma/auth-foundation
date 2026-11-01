// verify-vendor.mjs — 判定テストを流す仕組みと、写し(vendoring)の確かめ。Node 用(画面には載せない)。
//
// 各アプリのテストからは:
//   import { verify } from '<写した場所>/auth_foundation/verify-vendor.mjs';
//   verify();   // 写しが手で直されていないか(MANIFEST.json)と、全部の判定テストを確かめる。だめなら例外
// コマンドからは: node <写した場所>/auth_foundation/verify-vendor.mjs
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import * as af from './auth-foundation.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

// JSON として同じか(配列は順番まで、オブジェクトはキーの順を問わない)
export function same(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every(function (x, i) { return same(x, b[i]); });
  }
  if (a !== null && b !== null && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return same(ka, kb) && ka.every(function (k) { return same(a[k], b[k]); });
  }
  return a === b;
}

function invoke(doc, c) {
  const args = c.args || {};
  const cat = 'catalog' in args ? args.catalog : doc.catalog;
  const snap = 'snapshot' in args ? args.snapshot : doc.snapshot;
  switch (c.call) {
    case 'validate_catalog': return af.validateCatalog(cat);
    case 'evaluate': return af.evaluate(cat, snap, args.user_id, args.permission, args.resource);
    case 'permissions_at': return af.permissionsAt(cat, snap, args.user_id, args.resource);
    case 'sites_with': return af.sitesWith(cat, snap, args.user_id, args.permission);
    case 'check_guard': return af.checkGuard(cat, args.before, args.after, args.actor_user_id, args.guard_permission);
    case 'make_audit_event': return af.makeAuditEvent(args.fields);
    case 'validate_audit_event': return af.validateAuditEvent(args.event);
    case 'audit_retention': return af.auditRetention(args.action);
    default: throw new Error('未知の call: ' + c.call);
  }
}

// 1件を流す。合えば null、合わなければ理由の文字列。
export function runCase(doc, c) {
  let got;
  try {
    got = invoke(doc, c);
  } catch (e) {
    if (!(e instanceof af.AuthFoundationError)) throw e;
    if ('expect_error' in c) return e.code === c.expect_error ? null : 'エラー ' + e.code + '(正解は ' + c.expect_error + ')';
    return 'エラー ' + e.code + '(正解は戻り値)';
  }
  if ('expect_error' in c) return '戻り値 ' + JSON.stringify(got) + '(正解はエラー ' + c.expect_error + ')';
  if (!same(got, c.expect)) return '戻り値 ' + JSON.stringify(got) + '\n    正解 ' + JSON.stringify(c.expect);
  return null;
}

// dir の判定テストをすべて流す。{ passed, failures }
export function runVectors(dir) {
  let passed = 0;
  const failures = [];
  const names = fs.readdirSync(dir).filter(function (n) { return n.endsWith('.json'); }).sort();
  if (!names.length) failures.push('判定テストが1つもありません: ' + dir);
  names.forEach(function (n) {
    const doc = JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
    doc.cases.forEach(function (c) {
      const why = runCase(doc, c);
      if (why === null) passed++;
      else failures.push(n + ' / ' + c.name + ': ' + why);
    });
  });
  return { passed: passed, failures: failures };
}

function sha256(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }

function listFiles(root) {
  const out = [];
  (function walk(d) {
    fs.readdirSync(d, { withFileTypes: true }).sort(function (a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; })
      .forEach(function (e) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else out.push(path.relative(root, p).split(path.sep).join('/'));
      });
  })(root);
  return out;
}

// MANIFEST.json と中身が一致するか。問題の配列を返す。
export function checkManifest(root) {
  const mpath = path.join(root, 'MANIFEST.json');
  if (!fs.existsSync(mpath)) return ['MANIFEST.json がありません: ' + root];
  const listed = JSON.parse(fs.readFileSync(mpath, 'utf8')).files || {};
  const problems = [];
  listFiles(root).forEach(function (rel) {
    if (rel === 'MANIFEST.json') return;
    if (!(rel in listed)) problems.push('MANIFEST.json に無いファイル: ' + rel);
    else if (sha256(path.join(root, rel)) !== listed[rel]) problems.push('写したときと中身が違う(手で直さない): ' + rel);
  });
  Object.keys(listed).forEach(function (rel) {
    if (!fs.existsSync(path.join(root, rel))) problems.push('写したファイルが無い: ' + rel);
  });
  return problems;
}

// 写しを確かめる。問題があれば例外(.problems に一覧)。通った判定テストの件数を返す。
export function verify(root) {
  root = root || HERE;
  const problems = checkManifest(root);
  const vpath = path.join(root, 'VERSION');
  if (fs.existsSync(vpath)) {
    const v = fs.readFileSync(vpath, 'utf8').trim();
    if (v !== af.VERSION) problems.push('VERSION(' + v + ')と部品の版(' + af.VERSION + ')が違う');
  }
  const r = runVectors(path.join(root, 'vectors'));
  const all = problems.concat(r.failures);
  if (all.length) {
    const err = new Error('auth_foundation の写しの確かめに失敗:\n  ' + all.join('\n  '));
    err.problems = all;
    throw err;
  }
  return r.passed;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const n = verify();
    console.log('auth_foundation ' + af.VERSION + ': 写しは正しく、判定テスト ' + n + ' 件が通った');
  } catch (e) {
    console.log(e.message);
    process.exitCode = 1;
  }
}
