// 判定テストに書けない、JS 版だけの扱い。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as af from '../auth-foundation.mjs';

const SRC = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'auth-foundation.mjs'), 'utf8');
const CAT = {
  features: { report: ['view', 'edit'], member: ['view', 'edit'], audit: ['view'] },
  roles: [
    { key: 'admin', rank: 2, audience: 'internal', perms: { report: ['view', 'edit'], member: ['view', 'edit'], audit: ['view'] } },
    { key: 'worker', rank: 1, audience: 'internal', perms: { report: ['view', 'edit'] } },
  ],
};

test('エラーは AuthFoundationError(Error を継ぎ、code を持つ)', () => {
  assert.throws(() => af.evaluate(CAT, { now: '2026-11-01T00:00:00Z' }, 'u1', 'report.view', { type: 'site', id: 'x' }),
    e => e instanceof af.AuthFoundationError && e instanceof Error && e.code === 'unknown_site');
});

test('対象の形の誤り', () => {
  for (const r of [null, 'org', ['org'], { type: 'site', id: 3 }, { type: 'site', id: '' }]) {
    assert.throws(() => af.evaluate(CAT, { now: '2026-11-01T00:00:00Z' }, 'u1', 'report.view', r), e => e.code === 'invalid_resource');
  }
});

test('記録がオブジェクトでない', () => {
  assert.deepEqual(af.validateAuditEvent([]), [{ code: 'invalid_type', field: 'event' }]);
  assert.throws(() => af.makeAuditEvent(null), e => e.code === 'invalid_audit_event');
  assert.throws(() => af.makeAuditEvent({ host_tenant_id: 't', action: 'member.created', target_type: 'user', target_id: 'u',
    created_at: '2026-11-01T00:00:00Z', after: { token: 'x' } }),
  e => e.code === 'invalid_audit_event' && JSON.stringify(e.detail) === JSON.stringify([{ code: 'secret_field', field: 'after.token' }]));
});

test('入力を書き換えない・戻り値は入力と共有しない', () => {
  const snap = { now: '2026-11-01T00:00:00Z', sites: [{ id: 's1', groups: [] }], groups: [],
    memberships: [{ user_id: 'u1', status: 'active' }], teams: [],
    assignments: [{ id: 'a1', principal: { type: 'user', id: 'u1' }, role: 'admin', scope: { type: 'org', id: 't' }, exclusions: [] }] };
  const before = JSON.stringify(snap);
  const r = af.evaluate(CAT, snap, 'u1', 'report.edit', { type: 'site', id: 's1' });
  r.paths[0].scope.type = 'changed';
  assert.equal(JSON.stringify(snap), before);
});

test('Object.prototype の名前を権限と取り違えない', () => {
  const snap = { now: '2026-11-01T00:00:00Z', sites: [], groups: [], memberships: [], teams: [], assignments: [] };
  assert.throws(() => af.evaluate(CAT, snap, 'u1', 'constructor.view', { type: 'org' }), e => e.code === 'unknown_permission');
  assert.throws(() => af.evaluate(CAT, snap, 'u1', 'report.toString', { type: 'org' }), e => e.code === 'unknown_permission');
});

test('画面と Workers で動く: Node の機能・Date・Math.random・ES2017 より新しい書き方を使わない', () => {
  const code = SRC.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  assert.doesNotMatch(code, /\bimport\b|\brequire\(/, 'ほかのモジュールを読まない');
  assert.doesNotMatch(code, /\bDate\b|Math\.random|\bprocess\b|\bBuffer\b/);
  assert.doesNotMatch(code, /\?\.|\?\?|\.\.\.|\*\*=?/, '?. ?? ... ** は ES2017 に無い');
});

test('将来の上限(300名・3,000拠点)で使える速さ', () => {
  const sites = Array.from({ length: 3000 }, (_, i) => ({ id: 's' + i, groups: ['g' + (i % 8)] }));
  const groups = Array.from({ length: 8 }, (_, i) => ({ id: 'g' + i }));
  const members = Array.from({ length: 300 }, (_, i) => ({ user_id: 'u' + i, status: 'active' }));
  const teams = Array.from({ length: 30 }, (_, i) => ({ id: 't' + i, members: Array.from({ length: 10 }, (_, j) => 'u' + (i * 10 + j)) }));
  const assigns = teams.map((t, i) => ({ id: 'a' + i, principal: { type: 'team', id: t.id }, role: 'worker',
    scope: { type: 'site_group', id: 'g' + (i % 8) }, exclusions: [] }))
    .concat(sites.map((s, i) => ({ id: 'd' + i, principal: { type: 'user', id: 'u' + (i % 300) }, role: 'worker',
      scope: { type: 'site', id: s.id }, exclusions: [] })));
  const snap = { now: '2026-11-01T00:00:00Z', sites, groups, memberships: members, teams, assignments: assigns };
  const t = performance.now();
  const got = af.sitesWith(CAT, snap, 'u0', 'report.edit');
  assert.ok(performance.now() - t < 2000);
  assert.equal(got.length, 380);
});
