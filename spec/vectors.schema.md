# 判定テストの形と細かな決まり

[docs/設計.md](../docs/設計.md) §3〜§4 を、判定テストで確かめられる細かさで決めたもの。Python 版と JS 版はこの文書と `vectors/*.json` に合わせる。食い違ったら判定テストが正。

## 1. ファイルの形

```json
{
  "name": "basic",
  "description": "何を確かめるか",
  "catalog": { },
  "snapshot": { },
  "cases": [
    { "name": "管理者は組織全体のユーザー管理ができる",
      "call": "evaluate",
      "args": { "user_id": "u1", "permission": "member.edit", "resource": { "type": "org" } },
      "expect": { "allowed": true, "reason": null, "paths": [ ] } },
    { "name": "未知の拠点はエラー",
      "call": "evaluate",
      "args": { "user_id": "u1", "permission": "report.view", "resource": { "type": "site", "id": "zzz" } },
      "expect_error": "unknown_site" }
  ]
}
```

- `catalog`・`snapshot` はファイルで共通の入力。`args` に `catalog`・`snapshot` があれば、その件だけそちらを使う
- 正解は `expect`(戻り値)か `expect_error`(エラーの種類)のどちらか1つ
- 比べ方: 配列は順番まで、オブジェクトはキーの順番を問わずに比べる
- `call` は snake_case で書く。JS 版では camelCase の関数に読み替える(`permissions_at` → `permissionsAt`)

| `call` | `args` | Python | JS |
|---|---|---|---|
| `validate_catalog` | (`catalog`) | `validate_catalog(catalog)` | `validateCatalog(catalog)` |
| `evaluate` | `user_id`・`permission`・`resource` | `evaluate(catalog, snapshot, user_id, permission, resource)` | `evaluate(...)` |
| `permissions_at` | `user_id`・`resource` | `permissions_at(catalog, snapshot, user_id, resource)` | `permissionsAt(...)` |
| `sites_with` | `user_id`・`permission` | `sites_with(catalog, snapshot, user_id, permission)` | `sitesWith(...)` |
| `check_guard` | `before`・`after`・`actor_user_id`・(`guard_permission`) | `check_guard(catalog, before, after, actor_user_id, guard_permission="member.edit")` | `checkGuard(catalog, before, after, actorUserId, guardPermission)` |
| `make_audit_event` | `fields` | `make_audit_event(fields)` | `makeAuditEvent(fields)` |
| `validate_audit_event` | `event` | `validate_audit_event(event)` | `validateAuditEvent(event)` |
| `audit_retention` | `action` | `audit_retention(action)` | `auditRetention(action)` |

**値の形**: 配列であるべき値(`sites`・`groups`・チームの `members`・拠点の `groups`・動詞の一覧など)が配列でなければ、空の配列とみなす(文字列を部分一致で読まない)。オブジェクトであるべき値がオブジェクトでなければ、空のオブジェクトとみなす。**整数**は、値が整数の数(`1` も `1.0` も整数。JS では見分けられないため)。真偽値は整数でない。

エラーは、Python は `AuthFoundationError`(`.code` にエラーの種類)、JS は `AuthFoundationError`(`Error` を継ぐ。`.code`)を投げる。

## 2. カタログ(`validate_catalog`)

戻り値は誤りの配列(誤りが無ければ空)。誤りは `{ "code": ..., (場所) }` の形で、次の順に並べる。

1. `features` の機能グループごと(書いた順)。動詞の一覧が配列でなければ → `{ "code": "invalid_list", "feature": f }`。配列なら動詞ごと(書いた順):
   - 動詞が `view` / `create` / `edit` / `approve` 以外 → `{ "code": "invalid_action", "feature": f, "action": a }`
   - 同じ動詞が2回 → `{ "code": "duplicate_action", "feature": f, "action": a }`
2. `member`・`audit` の順に、`features` に無ければ → `{ "code": "missing_required_feature", "feature": f }`
3. `roles` のロールごと(書いた順):
   - key がそれより前のロールと同じ → `{ "code": "duplicate_role", "role": key }`
   - `audience` が `internal` / `partner` / `owner` 以外 → `{ "code": "invalid_audience", "role": key }`
   - `rank` が整数でない → `{ "code": "invalid_rank", "role": key }`
   - `perms` の機能グループごと(書いた順): `features` に無い → `{ "code": "unknown_feature", "role": key, "feature": f }`。動詞の一覧が配列でない → `{ "code": "invalid_list", "role": key, "feature": f }`。配列なら動詞ごと(書いた順)に、その機能グループに無い → `{ "code": "unknown_action", "role": key, "feature": f, "action": a }`

## 3. 判定(`evaluate`)

### 3-1. 確かめる順と、エラーの種類

1. `permission` が `feature.action` の形で、カタログの `features` にある → 無ければ `unknown_permission`
2. `resource` が `{type: "org"}` か `{type: "site", id}` → ほかは `invalid_resource`
3. `snapshot.now` が時刻の形(§5) → 違えば `invalid_time`
4. `snapshot.sites` に同じ ID が2つ → `duplicate_site`。`resource` の拠点が無い → `unknown_site`
5. `snapshot.memberships` に同じ `user_id` が2つ → `duplicate_membership`
6. 本人の所属が無い、または `status` が `active` でない → 断る(`not_member`)。ここで終わる
7. 割当を集める(下の 3-2)。集めた割当について:
   - `role` がカタログに無い → `unknown_role`
   - `scope.type` が `org` / `site_group` / `site` / `equipment` 以外 → `invalid_scope`
   - `scope` が `site` で、その拠点が `sites` に無い → `unknown_site`。`site_group` で、そのグループが `groups` に無い → `unknown_group`(`equipment` の ID は確かめない)
   - 除外の `type` が `site` / `site_group` 以外 → `invalid_exclusion`。除外の拠点・グループが無い → `unknown_site` / `unknown_group`
   - `expires_at`・`revoked_at` が null でも時刻の形でもない → `invalid_time`
8. 生きていない割当を落とし、範囲と除外を当て、和集合を取る(3-3)

エラーは見つけた順に最初の1つだけを投げる。

### 3-2. 割当を集める

`snapshot.assignments` を順に見て、次のどちらかに当たるものを集める。

- `principal.type = "user"` で `principal.id` が本人
- `principal.type = "team"` で、`snapshot.teams` に `principal.id` のチームがあり、その `members` に本人がいる(チームが見つからなければ集めない。エラーにしない)

`principal.type` がそれ以外(`collaboration` など)の割当は集めない。

### 3-3. 生きている割当・届く割当

- **生きている**: `expires_at` が null か `now` より後、かつ `revoked_at` が null か `now` より後、かつ `scope.type` が `equipment` でない。`now` と同じ時刻は「過ぎた」とする
- **届く**: 生きている割当のうち、
  - 対象が組織全体(`org`)なら、`scope.type = "org"` のものだけ。除外リストは当てない
  - 対象が拠点 S なら、`org`、S が属するグループの `site_group`、S そのものの `site`。そのうえで、除外リストのどれか(S そのもの、または S が属するグループ)に当たるものを落とす

### 3-4. 結果

- 届く割当のうち、ロールの `perms` が `permission` を持つものがあれば `allowed: true`、`reason: null`。`paths` はそれらの割当の経路(`snapshot.assignments` の順)
- 無ければ `allowed: false`、`paths: []`。`reason` は、生きている割当のどれか(範囲を問わず、除外を当てる前)のロールが `permission` を持っていれば `out_of_scope`、持っていなければ `no_permission`

経路の形:

```json
{ "assignment_id": "a1", "via": { "type": "team", "id": "t1" }, "scope": { "type": "site_group", "id": "g1" }, "role": "field_worker", "direct": false }
```

- `via` は直接の割当なら null
- `scope` は割当の `scope` の `type` と `id`(`org` のとき `id` は null)
- `direct` は `principal.type = "user"` なら true

## 4. ほかの関数

- `permissions_at`: `evaluate` と同じ確かめ方(1・2 以外の permission の確かめは無い)。所属が無ければ `{}`。あれば `{ feature: { action: [path, ...] } }` で、権限を持つ機能グループと動詞だけを入れる
- `sites_with`: 所属が無ければ `[]`。あれば `snapshot.sites` の順で、`evaluate` が許す拠点の ID の配列
- `check_guard`: 先に `guard_permission` を `evaluate` の 1 と同じく確かめる(`unknown_permission`)。そのあと `before`・`after` のそれぞれで、有効な所属を持つユーザーのうち `evaluate(guard_permission, {type: "org"})` が許す人を「守る権限を持つ人」とする。違反を次の順に返す
  - `after` で守る権限を持つ人が0人 → `{ "code": "no_admin_left" }`
  - `actor_user_id` が `before` で守る権限を持ち、`after` で持たない → `{ "code": "self_lockout" }`

## 5. 時刻の形

`YYYY-MM-DDTHH:MM:SS` に、任意で小数(1〜6桁)、そのあとに `Z` か `+HH:MM` / `-HH:MM` を付けた形。時差は必須。日付だけ・時差なしはエラー(`invalid_time`)。存在しない日付(2月30日など)・範囲外の時分秒(24時、60秒)・範囲外の時差(±24時以上)もエラー。比べるときは、時差を引いた絶対の時刻(マイクロ秒)で比べる。

## 6. 監査ログ

### 6-1. 項目

| 項目 | 必須か | 型 |
|---|---|---|
| `id` | 任意(無い・null も可) | 文字列か整数 |
| `host_tenant_id` | 必須 | 空でない文字列 |
| `actor_user_id` | 任意(無い・null も可) | 文字列 |
| `actor_tenant_id` | 必須 | 空でない文字列 |
| `action` | 必須 | 空でない文字列。§6-2 |
| `target_type` | 必須 | 空でない文字列 |
| `target_id` | 必須 | 空でない文字列 |
| `before` | 任意(無い・null も可) | オブジェクト |
| `after` | 任意(無い・null も可) | オブジェクト |
| `ip_address` | 任意(無い・null も可) | 文字列 |
| `created_at` | 必須 | 時刻の形(§5) |

### 6-2. `validate_audit_event`

戻り値は誤りの配列。記録がオブジェクトでなければ `[{ "code": "invalid_type", "field": "event" }]` だけを返す。オブジェクトなら次の順に並べる。

1. 上の表の順に項目ごと:
   - 必須なのに無い・null → `{ "code": "missing_field", "field": f }`
   - 型が違う(必須の文字列が空も含む) → `{ "code": "invalid_type", "field": f }`
   - `created_at` が時刻の形でない → `{ "code": "invalid_time", "field": "created_at" }`
   - `action` が `audit-actions.json` の `actions` に無く、`patterns` のどれにも当たらない → `{ "code": "unknown_action", "field": "action" }`
2. `before`・`after` の順に、中を深さ優先で(オブジェクトはキーの順、配列は番号の順)見て、秘密のキーがあれば → `{ "code": "secret_field", "field": "after.user.password_hash" }`(配列の番号も `.0` の形で入れる)。秘密のキーとは、名前を単語に分けたとき(大文字の前で区切り(`passwordHash` → `password`・`Hash`)、小文字にして英数字以外で区切る)、どれかの単語が `password`・`passwd`・`pwd`・`secret`・`token`・`session`・`otp`・`code` か、その語に `s` を付けたものであるもの。`verification_code`・`access-tokens`・`SessionID` は秘密、`footprint`・`barcode`・`tokenless` は秘密でない。業務の ID に `site_code` のような名前を使うと秘密とみなされるので、記録では `site_id` などにする
3. 表に無い項目(書いた順) → `{ "code": "unknown_field", "field": f }`

### 6-3. `make_audit_event`

`fields` から、表の11項目をすべて持つ記録を作る。無い任意の項目は null、`actor_tenant_id` が無ければ `host_tenant_id` と同じにする。`fields` にある表に無い項目もそのまま入れる。作った記録を `validate_audit_event` で確かめ、誤りがあれば `invalid_audit_event` を投げる(誤りの配列をエラーに添える。Python は `.detail`、JS は `.detail`)。`fields` がオブジェクトでなくても `invalid_audit_event`。

### 6-4. `audit_retention`

操作名の保存期間を返す。`"indefinite"`(無期限)か `"13_months"`。`actions` にあればその値、`patterns` に当たればその値。どれにも当たらなければ `unknown_action` を投げる。
