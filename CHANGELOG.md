# 変更の記録

版の番号の決め方は [docs/設計.md](docs/設計.md) §6-1。

## 1.0.0(作成中)

- 最初の版。権限の判定(`evaluate`・`permissions_at`・`sites_with`)、変更の守り(`check_guard`)、カタログの確認(`validate_catalog`)、監査ログの形(`make_audit_event`・`validate_audit_event`・`audit_retention`)
- Python 版と JS 版。同じ判定テスト(`spec/vectors/`)を通す
- 写し取り用のスクリプト `tools/vendor.py`
