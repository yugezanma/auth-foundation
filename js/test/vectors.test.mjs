// spec/vectors/ の判定テストをすべて JS 版で流す。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as af from '../auth-foundation.mjs';
import { runCase } from '../verify-vendor.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const VECTORS = path.join(ROOT, 'spec', 'vectors');

for (const n of fs.readdirSync(VECTORS).filter(x => x.endsWith('.json')).sort()) {
  const doc = JSON.parse(fs.readFileSync(path.join(VECTORS, n), 'utf8'));
  test(n, () => {
    const failures = [];
    for (const c of doc.cases) {
      const why = runCase(doc, c);
      if (why !== null) failures.push(c.name + ': ' + why);
    }
    assert.deepEqual(failures, []);
  });
}

test('VERSION ファイルと部品の版が同じ', () => {
  assert.equal(fs.readFileSync(path.join(ROOT, 'VERSION'), 'utf8').trim(), af.VERSION);
});

test('監査ログの操作名が spec/audit-actions.json と同じ', () => {
  const spec = JSON.parse(fs.readFileSync(path.join(ROOT, 'spec', 'audit-actions.json'), 'utf8'));
  assert.deepEqual(af.AUDIT_ACTIONS, spec.actions.map(a => [a.name, a.required, a.retention, a.reserved]));
  assert.deepEqual(af.AUDIT_PATTERNS, spec.patterns.map(p => [p.pattern, p.required, p.retention]));
});
