# 変更の記録

版の番号の決め方は [docs/設計.md](docs/設計.md) §6-1。

## 1.0.0(2026-11-02)

最初の版。

- 判定: `evaluate`・`permissions_at`・`sites_with`(和集合。範囲は組織全体・グループ・拠点、除外リスト、期限・失効。断る理由は `not_member` / `out_of_scope` / `no_permission`、経路は構造で返す)
- 変更の守り: `check_guard`(`no_admin_left`・`self_lockout`)
- カタログの確認: `validate_catalog`
- 監査ログ: `make_audit_event`・`validate_audit_event`・`audit_retention`、操作名の一覧 `spec/audit-actions.json`(拠点の増減 `site.*`、運営側のテナントの操作 `tenant.*`、サポートの閲覧 `support_access.*` を含む)
- テナント: 1つのスナップショットは1つのテナントのデータ。テナントが複数のアプリは、セッションのテナントでスナップショットを作る。運営側(当社)はお客様のテナントに所属せず、お客様のデータは許可があるときだけ見るだけで見る(設計.md §3-8。判定の外)
- 予約(判定には効かない): `collaboration` の割当、`equipment` の範囲、`audience`、`is_tenant_admin`、`is_billable`
- Python 版(3.11 以上)と JS 版(ES2017・依存なし)。同じ判定テスト(`spec/vectors/`、17ファイル・537件)を通す。電力データ集計の今の判定(`pda.json`)、SolarOM の `perm-data.js` の判定(`solarom.json`)、テナントが分かれていること(`tenants.json`)を含む
- 写し取り用のスクリプト `tools/vendor.py` と、写しの確かめ(`verify_vendor.py`・`verify-vendor.mjs`)
