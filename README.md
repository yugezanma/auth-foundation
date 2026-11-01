# auth-foundation

2つのアプリ(電力データ集計・SolarOM)で共通に使う、ユーザー管理(認証・権限)の**仕組み**。共通仕様・判定の部品(Python 版と JS 版)・判定テストを置く。利用者のデータは置かない。

- 設計: [docs/設計.md](docs/設計.md)
- 実装計画: [docs/実装計画.md](docs/実装計画.md)
- 判定テストの形と決まり: [spec/vectors.schema.md](spec/vectors.schema.md)
- 変更の記録: [CHANGELOG.md](CHANGELOG.md)

## 中身

| パス | 中身 |
|---|---|
| `spec/vectors/*.json` | 判定テスト(入力と正解)。Python 版と JS 版が同じものを通す |
| `spec/audit-actions.json` | 監査ログの操作名・必須か・保存期間 |
| `python/auth_foundation/` | Python 版(標準ライブラリだけ。Python 3.11 以上) |
| `js/auth-foundation.mjs` | JS 版(ES モジュール1つ。依存なし) |
| `tools/vendor.py` | 各アプリへ写すスクリプト |
| `tools/check.sh` | 両方のテストをまとめて流す |

## テスト

```sh
tools/check.sh
```

Python は `python3 -m unittest`、JS は `node --test`(Node 20 以上)。どちらも外部の依存は無い。
