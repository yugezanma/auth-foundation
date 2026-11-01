// auth-foundation.mjs — ユーザー管理(認証・権限)の共通の部品。JS 版。
// 設計は docs/設計.md、細かな決まりは spec/vectors.schema.md。Python 版と同じ判定テストを通す。
// 副作用を持たない関数だけを置く。ES2017 の範囲で書き、ビルドしない。Date・Math.random を使わない。

export const VERSION = '1.0.0-dev';
export const VERBS = ['view', 'create', 'edit', 'approve'];
const REQUIRED_FEATURES = ['member', 'audit'];
const AUDIENCES = ['internal', 'partner', 'owner'];
const SCOPE_TYPES = ['org', 'site_group', 'site', 'equipment'];
const EXCLUSION_TYPES = ['site', 'site_group'];

export class AuthFoundationError extends Error {
  constructor(code, detail) {
    super(detail === undefined ? code : code + ': ' + safeString(detail));
    this.name = 'AuthFoundationError';
    this.code = code;
    this.detail = detail === undefined ? null : detail;
  }
}

function safeString(v) {
  try { return typeof v === 'string' ? v : JSON.stringify(v); } catch (e) { return String(v); }
}
function own(o, k) { return o !== null && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k); }
function get(o, k) { return own(o, k) ? o[k] : undefined; }
function isNil(v) { return v === null || v === undefined; }
function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
function list(v) { return Array.isArray(v) ? v : []; }
function has(arr, v) { return list(arr).indexOf(v) >= 0; }

// ==================== 時刻(spec §5) ====================
const TIME_RE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?(Z|([+-])([0-9]{2}):([0-9]{2}))$/;
const DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
function leap(y) { return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0); }
function daysFromCivil(y, m, d) {
  y -= m <= 2 ? 1 : 0;
  const era = Math.floor(y / 400);
  const yoe = y - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}
// 時刻を [秒, マイクロ秒] にする。形が違えば null。
export function parseTime(value) {
  if (typeof value !== 'string') return null;
  const m = TIME_RE.exec(value);
  if (!m) return null;
  const y = +m[1], mo = +m[2], d = +m[3], h = +m[4], mi = +m[5], s = +m[6];
  if (mo < 1 || mo > 12 || d < 1 || h > 23 || mi > 59 || s > 59) return null;
  const dim = mo === 2 && leap(y) ? 29 : DAYS[mo - 1];
  if (d > dim) return null;
  let off = 0;
  if (m[8] !== 'Z') {
    const oh = +m[10], om = +m[11];
    if (oh > 23 || om > 59) return null;
    off = (oh * 3600 + om * 60) * (m[9] === '+' ? 1 : -1);
  }
  const secs = daysFromCivil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s - off;
  const micros = +((m[7] || '') + '000000').slice(0, 6);
  return [secs, micros];
}
function requireTime(v) {
  const t = parseTime(v);
  if (t === null) throw new AuthFoundationError('invalid_time', v);
  return t;
}
function later(a, b) { return a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]); }

// ==================== カタログ(spec §2) ====================
export function validateCatalog(catalog) {
  const out = [];
  const features = get(catalog, 'features') || {};
  Object.keys(features).forEach(function (f) {
    const seen = [];
    list(features[f]).forEach(function (a) {
      if (VERBS.indexOf(a) < 0) out.push({ code: 'invalid_action', feature: f, action: a });
      else if (seen.indexOf(a) >= 0) out.push({ code: 'duplicate_action', feature: f, action: a });
      seen.push(a);
    });
  });
  REQUIRED_FEATURES.forEach(function (f) {
    if (!own(features, f)) out.push({ code: 'missing_required_feature', feature: f });
  });
  const keys = [];
  list(get(catalog, 'roles')).forEach(function (r) {
    const key = get(r, 'key');
    if (keys.indexOf(key) >= 0) out.push({ code: 'duplicate_role', role: key });
    keys.push(key);
    if (AUDIENCES.indexOf(get(r, 'audience')) < 0) out.push({ code: 'invalid_audience', role: key });
    if (!Number.isInteger(get(r, 'rank'))) out.push({ code: 'invalid_rank', role: key });
    const perms = get(r, 'perms') || {};
    Object.keys(perms).forEach(function (f) {
      if (!own(features, f)) { out.push({ code: 'unknown_feature', role: key, feature: f }); return; }
      list(perms[f]).forEach(function (a) {
        if (!has(features[f], a)) out.push({ code: 'unknown_action', role: key, feature: f, action: a });
      });
    });
  });
  return out;
}

// ==================== 判定(spec §3〜§4) ====================
function parsePermission(catalog, permission) {
  if (typeof permission !== 'string' || permission.split('.').length !== 2) {
    throw new AuthFoundationError('unknown_permission', permission);
  }
  const parts = permission.split('.');
  const features = get(catalog, 'features') || {};
  if (!own(features, parts[0]) || !has(features[parts[0]], parts[1])) {
    throw new AuthFoundationError('unknown_permission', permission);
  }
  return parts;
}

function parseResource(resource) {
  if (isObj(resource)) {
    const t = get(resource, 'type');
    if (t === 'org') return ['org', null];
    const id = get(resource, 'id');
    if (t === 'site' && typeof id === 'string' && id !== '') return ['site', id];
  }
  throw new AuthFoundationError('invalid_resource', resource);
}

// 1人分の判定の下ごしらえ。所属・生きている割当を一度だけ求める。
function Context(catalog, snapshot, userId, resource) {
  const now = requireTime(get(snapshot, 'now'));
  const sites = new Map();
  list(get(snapshot, 'sites')).forEach(function (s) {
    const id = get(s, 'id');
    if (sites.has(id)) throw new AuthFoundationError('duplicate_site', id);
    sites.set(id, list(get(s, 'groups')).slice());
  });
  this.sites = sites;
  if (resource && resource[0] === 'site' && !sites.has(resource[1])) {
    throw new AuthFoundationError('unknown_site', resource[1]);
  }
  let status = null;
  const seen = new Set();
  list(get(snapshot, 'memberships')).forEach(function (m) {
    const uid = get(m, 'user_id');
    if (seen.has(uid)) throw new AuthFoundationError('duplicate_membership', uid);
    seen.add(uid);
    if (uid === userId) status = get(m, 'status');
  });
  this.member = status === 'active';
  this.alive = [];
  if (!this.member) return;
  const roles = new Map();
  list(get(catalog, 'roles')).forEach(function (r) {
    if (!roles.has(get(r, 'key'))) roles.set(get(r, 'key'), get(r, 'perms') || {});
  });
  const groups = new Set(list(get(snapshot, 'groups')).map(function (g) { return get(g, 'id'); }));
  const teams = new Map();
  list(get(snapshot, 'teams')).forEach(function (t) {
    if (!teams.has(get(t, 'id'))) teams.set(get(t, 'id'), list(get(t, 'members')));
  });
  const self = this;
  list(get(snapshot, 'assignments')).forEach(function (a) {
    const p = get(a, 'principal') || {};
    let team;
    if (get(p, 'type') === 'user' && get(p, 'id') === userId) team = null;
    else if (get(p, 'type') === 'team' && teams.has(get(p, 'id')) && teams.get(get(p, 'id')).indexOf(userId) >= 0) team = get(p, 'id');
    else return;
    const e = self.check(a, roles, groups);
    e.team = team;
    // 両方を先に読む(片方で落ちても、もう片方の形の誤りを見逃さない)
    const ts = ['expires_at', 'revoked_at'].filter(function (k) { return !isNil(get(a, k)); })
      .map(function (k) { return requireTime(a[k]); });
    const live = ts.every(function (t) { return later(t, now); });
    if (live && e.scopeType !== 'equipment') self.alive.push(e);
  });
}

Context.prototype.check = function (a, roles, groups) {
  const role = get(a, 'role');
  if (!roles.has(role)) throw new AuthFoundationError('unknown_role', role);
  const scope = get(a, 'scope') || {};
  const st = get(scope, 'type'), sid = get(scope, 'id');
  if (SCOPE_TYPES.indexOf(st) < 0) throw new AuthFoundationError('invalid_scope', st);
  this.checkTarget(st, sid, groups);
  const self = this;
  const excl = list(get(a, 'exclusions')).map(function (x) {
    const t = get(x, 'type'), i = get(x, 'id');
    if (EXCLUSION_TYPES.indexOf(t) < 0) throw new AuthFoundationError('invalid_exclusion', t);
    self.checkTarget(t, i, groups);
    return [t, i];
  });
  return { assignmentId: get(a, 'id'), scopeType: st, scopeId: st === 'org' ? null : sid,
    exclusions: excl, role: role, perms: roles.get(role), team: null };
};

Context.prototype.checkTarget = function (t, i, groups) {
  if (t === 'site' && !this.sites.has(i)) throw new AuthFoundationError('unknown_site', i);
  if (t === 'site_group' && !groups.has(i)) throw new AuthFoundationError('unknown_group', i);
};

Context.prototype.reaches = function (e, resource) {
  if (resource[0] === 'org') return e.scopeType === 'org';
  const site = resource[1];
  const groups = this.sites.get(site);
  if (!(e.scopeType === 'org'
    || (e.scopeType === 'site_group' && groups.indexOf(e.scopeId) >= 0)
    || (e.scopeType === 'site' && e.scopeId === site))) return false;
  return !e.exclusions.some(function (x) {
    return (x[0] === 'site' && x[1] === site) || (x[0] === 'site_group' && groups.indexOf(x[1]) >= 0);
  });
};

function grants(e, f, a) { return own(e.perms, f) && has(e.perms[f], a); }

Context.prototype.paths = function (f, a, resource) {
  const self = this;
  return this.alive.filter(function (e) { return grants(e, f, a) && self.reaches(e, resource); }).map(toPath);
};

Context.prototype.decide = function (f, a, resource) {
  if (!this.member) return { allowed: false, reason: 'not_member', paths: [] };
  const ps = this.paths(f, a, resource);
  if (ps.length) return { allowed: true, reason: null, paths: ps };
  const held = this.alive.some(function (e) { return grants(e, f, a); });
  return { allowed: false, reason: held ? 'out_of_scope' : 'no_permission', paths: [] };
};

function toPath(e) {
  return { assignment_id: e.assignmentId, via: e.team !== null ? { type: 'team', id: e.team } : null,
    scope: { type: e.scopeType, id: e.scopeId }, role: e.role, direct: e.team === null };
}

// その人がその対象でその権限を持つか。{ allowed, reason, paths }
export function evaluate(catalog, snapshot, userId, permission, resource) {
  const p = parsePermission(catalog, permission);
  const res = parseResource(resource);
  return new Context(catalog, snapshot, userId, res).decide(p[0], p[1], res);
}

// その対象で持つ権限すべてと経路。{ feature: { action: [path, ...] } }
export function permissionsAt(catalog, snapshot, userId, resource) {
  const res = parseResource(resource);
  const ctx = new Context(catalog, snapshot, userId, res);
  const out = {};
  if (!ctx.member) return out;
  const features = get(catalog, 'features') || {};
  Object.keys(features).forEach(function (f) {
    list(features[f]).forEach(function (a) {
      const ps = ctx.paths(f, a, res);
      if (ps.length) { out[f] = out[f] || {}; out[f][a] = ps; }
    });
  });
  return out;
}

// その権限が届く拠点の ID の配列(snapshot.sites の順)
export function sitesWith(catalog, snapshot, userId, permission) {
  const p = parsePermission(catalog, permission);
  const ctx = new Context(catalog, snapshot, userId, null);
  if (!ctx.member) return [];
  const out = [];
  ctx.sites.forEach(function (_, sid) { if (ctx.paths(p[0], p[1], ['site', sid]).length) out.push(sid); });
  return out;
}

// 変更の前と後をくらべて、違反(no_admin_left・self_lockout)の配列を返す
export function checkGuard(catalog, before, after, actorUserId, guardPermission) {
  const p = parsePermission(catalog, guardPermission === undefined ? 'member.edit' : guardPermission);
  function holders(snapshot) {
    const out = new Set();
    list(get(snapshot, 'memberships')).forEach(function (m) {
      const uid = get(m, 'user_id');
      if (get(m, 'status') === 'active'
        && new Context(catalog, snapshot, uid, null).decide(p[0], p[1], ['org', null]).allowed) out.add(uid);
    });
    return out;
  }
  const hb = holders(before), ha = holders(after);
  const out = [];
  if (ha.size === 0) out.push({ code: 'no_admin_left' });
  if (hb.has(actorUserId) && !ha.has(actorUserId)) out.push({ code: 'self_lockout' });
  return out;
}

// ==================== 監査ログ(spec §6) ====================
// spec/audit-actions.json と同じ一覧(テストで突き合わせる)。[名前, 必須か, 保存期間, 予約か]
export const AUDIT_ACTIONS = [
  ["auth.login.succeeded", true, "13_months", false],
  ["auth.login.failed", true, "13_months", false],
  ["auth.logout", false, "13_months", false],
  ["auth.password.changed", true, "13_months", false],
  ["auth.password.reset", true, "13_months", false],
  ["member.created", true, "indefinite", false],
  ["member.updated", true, "indefinite", false],
  ["member.suspended", true, "indefinite", false],
  ["member.reactivated", true, "indefinite", false],
  ["member.password_set", true, "indefinite", false],
  ["member.invited", true, "indefinite", false],
  ["assignment.created", true, "indefinite", false],
  ["assignment.updated", true, "indefinite", false],
  ["assignment.revoked", true, "indefinite", false],
  ["role.changed", false, "indefinite", false],
  ["team.created", true, "indefinite", false],
  ["team.updated", true, "indefinite", false],
  ["team.archived", true, "indefinite", false],
  ["team.member_added", true, "indefinite", false],
  ["team.member_removed", true, "indefinite", false],
  ["site.created", true, "indefinite", false],
  ["site.archived", true, "indefinite", false],
  ["site.unarchived", true, "indefinite", false],
  ["collaboration.invited", false, "indefinite", true],
  ["collaboration.accepted", false, "indefinite", true],
  ["collaboration.suspended", false, "indefinite", true],
  ["collaboration.ended", false, "indefinite", true],
  ["report.published", false, "indefinite", true],
  ["report.unpublished", false, "indefinite", true],
  ["view_as.started", false, "indefinite", true]
];
// [正規表現, 必須か, 保存期間]。AUDIT_ACTIONS に無い名前に、上から順に当てる
export const AUDIT_PATTERNS = [
  ["^[a-z][a-z0-9_]*\\.(archived|unarchived)$", true, "indefinite"],
  ["^app(\\.[a-z][a-z0-9_]*)+$", false, "13_months"]
];
const BY_NAME = new Map(AUDIT_ACTIONS.map(function (a) { return [a[0], a]; }));
const COMPILED = AUDIT_PATTERNS.map(function (p) { return [new RegExp(p[0]), p[1], p[2]]; });
const FIELDS = [
  ['id', false, 'id'], ['host_tenant_id', true, 'str'], ['actor_user_id', false, 'str'],
  ['actor_tenant_id', true, 'str'], ['action', true, 'action'], ['target_type', true, 'str'],
  ['target_id', true, 'str'], ['before', false, 'obj'], ['after', false, 'obj'],
  ['ip_address', false, 'str'], ['created_at', true, 'time'],
];
const FIELD_NAMES = FIELDS.map(function (f) { return f[0]; });
const SECRET_WORDS = ['password', 'passwd', 'secret', 'token', 'session', 'otp'];

function lookupAction(action) {
  if (typeof action !== 'string') return null;
  if (BY_NAME.has(action)) { const a = BY_NAME.get(action); return { required: a[1], retention: a[2] }; }
  for (let i = 0; i < COMPILED.length; i++) {
    if (COMPILED[i][0].test(action)) return { required: COMPILED[i][1], retention: COMPILED[i][2] };
  }
  return null;
}

// 操作名の保存期間('indefinite' か '13_months')
export function auditRetention(action) {
  const info = lookupAction(action);
  if (info === null) throw new AuthFoundationError('unknown_action', action);
  return info.retention;
}

function isSecret(key) {
  const k = String(key).toLowerCase();
  return k === 'code' || SECRET_WORDS.some(function (w) { return k.indexOf(w) >= 0; });
}

function scan(value, prefix, out) {
  if (Array.isArray(value)) {
    value.forEach(function (v, i) { scan(v, prefix + '.' + i, out); });
  } else if (isObj(value)) {
    Object.keys(value).forEach(function (k) {
      const name = prefix + '.' + k;
      if (isSecret(k)) out.push({ code: 'secret_field', field: name });
      else scan(value[k], name, out);
    });
  }
}

// 監査ログの記録の誤りの配列を返す(誤りが無ければ空)
export function validateAuditEvent(event) {
  if (!isObj(event)) return [{ code: 'invalid_type', field: 'event' }];
  const out = [];
  FIELDS.forEach(function (fd) {
    const name = fd[0], required = fd[1], kind = fd[2];
    const v = get(event, name);
    if (isNil(v)) { if (required) out.push({ code: 'missing_field', field: name }); return; }
    if (kind === 'time') {
      if (parseTime(v) === null) out.push({ code: 'invalid_time', field: name });
    } else if (kind === 'id') {
      if (!(typeof v === 'string' || Number.isInteger(v))) out.push({ code: 'invalid_type', field: name });
    } else if (kind === 'obj') {
      if (!isObj(v)) out.push({ code: 'invalid_type', field: name });
    } else if (typeof v !== 'string' || (required && v === '')) {
      out.push({ code: 'invalid_type', field: name });
    } else if (kind === 'action' && lookupAction(v) === null) {
      out.push({ code: 'unknown_action', field: name });
    }
  });
  ['before', 'after'].forEach(function (name) { if (isObj(get(event, name))) scan(event[name], name, out); });
  Object.keys(event).forEach(function (k) {
    if (FIELD_NAMES.indexOf(k) < 0) out.push({ code: 'unknown_field', field: k });
  });
  return out;
}

// 表の11項目をすべて持つ記録を作る。誤りがあれば invalid_audit_event を投げる
export function makeAuditEvent(fields) {
  if (!isObj(fields)) throw new AuthFoundationError('invalid_audit_event', [{ code: 'invalid_type', field: 'event' }]);
  const event = {};
  FIELD_NAMES.forEach(function (k) { const v = get(fields, k); event[k] = isNil(v) ? null : v; });
  if (event.actor_tenant_id === null) event.actor_tenant_id = event.host_tenant_id;
  Object.keys(fields).forEach(function (k) { if (!own(event, k)) event[k] = fields[k]; });
  const errors = validateAuditEvent(event);
  if (errors.length) throw new AuthFoundationError('invalid_audit_event', errors);
  return event;
}
