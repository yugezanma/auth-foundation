// SolarOM の権限管理デモ(デモアプリ/admin/js/perm-data.js)の判定を、共通の形に当てはめた判定テストを書き出す。
//
// 正解は perm-data.js を実際に動かして作る(共通の部品からは作らない):
//   経路 = assignmentsFor(user) のうち assignmentSites(a) に拠点を含むもの(割当の順)、
//   権限 = そのロールの perms。permissionsAt と同じ集め方で、経路を表示の文字列ではなく構造で持つ。
// 違いは1つだけ: perm-data.js の permissionsAt はユーザーの status を見ないが、共通仕様では
// 招待中(u11)・停止中(u12)は not_member なので、その2人の正解は空にする(設計.md §3-4 の1)。
//
// 使い方: node tools/vectors/make_solarom.mjs <solar-om のパス> spec/vectors
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const [solar, out] = process.argv.slice(2);
const src = fs.readFileSync(path.join(solar, 'デモアプリ/admin/js/perm-data.js'), 'utf8');
const ctx = { window: {} };
vm.runInNewContext(src, ctx);
const PD = ctx.window.PermData;

// 判定に効く拠点だけを抜き出す(割当の範囲に出てくる拠点・各エリア・重点管理を含む)
const SITE_IDS = ['s001', 's005', 's013', 's040', 's041', 's053', 's081', 's082', 's093', 's120'];
const FEATURES = {
  inspection: ['view', 'create', 'edit', 'approve'], defect: ['view', 'create', 'edit', 'approve'],
  asset_master: ['view', 'create', 'edit'], report: ['view', 'create', 'edit', 'approve'],
  contract: ['view', 'create', 'edit'], member: ['view', 'create', 'edit'], audit: ['view'],
};
const catalog = {
  features: FEATURES,
  roles: PD.ROLES.map(r => ({ key: r.key, rank: r.rank, audience: 'internal', perms: JSON.parse(JSON.stringify(r.perms)) })),
};
const plain = v => JSON.parse(JSON.stringify(v));
const snapshot = {
  tenant_id: 'solarom-demo',
  now: '2026-08-13T09:00:00+09:00',
  sites: SITE_IDS.map(id => ({ id, groups: plain(PD.site(id).groups) })),
  groups: PD.GROUPS.map(g => ({ id: g.id })),
  memberships: PD.USERS.map(u => ({ user_id: u.id, status: u.status })),
  teams: PD.TEAMS.map(t => ({ id: t.id, members: plain(t.members) })),
  assignments: PD.ASSIGNMENTS.map(a => ({
    id: a.id, principal: plain(a.principal), role: a.roleKey,
    scope: { type: a.scope.type, id: a.scope.id },
    exclusions: a.exclusions.map(e => ({ type: e.type, id: e.id })),
    expires_at: null, revoked_at: null, granted_by: a.grantedBy, created_at: a.createdAt + 'T09:00:00+09:00',
  })),
};

const active = id => PD.user(id).status === 'active';
function expectedAt(userId, siteId) {
  if (!active(userId)) return {};
  const outp = {};
  for (const x of PD.assignmentsFor(userId)) {
    const a = x.assignment;
    if (PD.assignmentSites(a).indexOf(siteId) < 0) continue;
    const r = PD.role(a.roleKey);
    const p = {
      assignment_id: a.id, via: a.principal.type === 'team' ? { type: 'team', id: a.principal.id } : null,
      scope: { type: a.scope.type, id: a.scope.id }, role: a.roleKey, direct: a.principal.type === 'user',
    };
    for (const fg of Object.keys(r.perms)) for (const act of r.perms[fg]) {
      outp[fg] = outp[fg] || {};
      (outp[fg][act] = outp[fg][act] || []).push(p);
    }
  }
  // perm-data.js と突き合わせる: 経路の表示の文字列が、permissionsAt と同じ集合になること
  const theirs = PD.permissionsAt(userId, siteId);
  const label = p => { const x = PD.assignmentsFor(userId).find(y => y.assignment.id === p.assignment_id); return PD.pathLabel(x); };
  const mine = {};
  for (const fg of Object.keys(outp)) for (const act of Object.keys(outp[fg])) {
    mine[fg] = mine[fg] || {}; mine[fg][act] = [...new Set(outp[fg][act].map(label))];
  }
  if (JSON.stringify(mine) !== JSON.stringify(plain(theirs))) {
    throw new Error('perm-data.js と合わない: ' + userId + ' ' + siteId);
  }
  return outp;
}

const cases = [];
for (const u of PD.USERS) for (const s of SITE_IDS) {
  cases.push({ name: `${u.id}(${u.name}・${u.status})/ ${s}(${PD.site(s).name})`, call: 'permissions_at',
    args: { user_id: u.id, resource: { type: 'site', id: s } }, expect: expectedAt(u.id, s) });
}
for (const u of PD.USERS) for (const perm of ['report.view', 'inspection.create', 'contract.edit']) {
  const [fg, act] = perm.split('.');
  const exp = SITE_IDS.filter(s => { const e = expectedAt(u.id, s); return !!(e[fg] && e[fg][act]); });
  cases.push({ name: `${u.id} の ${perm} が届く拠点`, call: 'sites_with', args: { user_id: u.id, permission: perm }, expect: exp });
}
const ev = (name, user, perm, res, expect) => cases.push({ name, call: 'evaluate', args: { user_id: user, permission: perm, resource: res }, expect });
ev('管理責任者はメンバー・権限を編集できる', 'u10', 'member.edit', { type: 'org' },
  { allowed: true, reason: null, paths: [{ assignment_id: 'a6', via: null, scope: { type: 'org', id: null }, role: 'admin', direct: true }] });
ev('閲覧者は重点管理(除外)の関西の発電所を見られない(関東は点検チームから届く)', 'u04', 'report.view', { type: 'site', id: 's053' }, { allowed: false, reason: 'out_of_scope', paths: [] });
ev('関東の発電所担当は関西を承認できない', 'u01', 'report.approve', { type: 'site', id: 's041' }, { allowed: false, reason: 'out_of_scope', paths: [] });
ev('事務・経理は点検を起票できない', 'u08', 'inspection.create', { type: 'site', id: 's001' }, { allowed: false, reason: 'no_permission', paths: [] });
ev('招待中の割当は効かない', 'u11', 'inspection.create', { type: 'site', id: 's081' }, { allowed: false, reason: 'not_member', paths: [] });

const doc = {
  name: 'solarom',
  description: 'SolarOM の権限管理デモ(perm-data.js、割当 a1〜a11)の判定を共通の形に当てはめたもの。拠点は判定に効く10件を抜き出した。'
    + 'perm-data.js の permissionsAt と経路の集合が同じ(作るときに突き合わせている)。違いは招待中(u11)・停止中(u12)を not_member とすることだけ',
  catalog, snapshot, cases,
};
fs.writeFileSync(path.join(out, 'solarom.json'), JSON.stringify(doc, null, 1) + '\n');
console.log('solarom', cases.length);
