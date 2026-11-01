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
| `tools/sync_audit_actions.py` | `spec/audit-actions.json` の操作名を両方の版へ書き込む |

## テスト

```sh
tools/check.sh
```

Python は `python3 -m unittest`、JS は `node --test`(Node 20 以上)。どちらも外部の依存は無い。

## 各アプリでの使い方

部品はパッケージとして配らず、タグの中身を各アプリへ**写す**(理由は [docs/設計.md](docs/設計.md) §6-2)。写しは手で直さない。

### 写す

このリポジトリで、使う版のタグを checkout してから実行する。

```sh
git checkout v1.0.0
python3 tools/vendor.py --lang python --dest <アプリの中の置き場所>   # 電力データ集計
python3 tools/vendor.py --lang js     --dest <アプリの中の置き場所>   # SolarOM
```

`<置き場所>/auth_foundation/` に次のものができ、写したあとにその場で確かめが流れる。

| ファイル | 中身 |
|---|---|
| 部品 | Python 版は `*.py`(パッケージ `auth_foundation`)、JS 版は `auth-foundation.mjs` |
| `vectors/*.json` | 判定テスト |
| `VERSION`・`MANIFEST.json` | 写した版、ファイルごとの SHA-256、もとのタグとコミット |
| `verify_vendor.py` / `verify-vendor.mjs` | 確かめ用のコード(ハッシュの一致と、全部の判定テスト) |
| `.gitattributes` | 取り込んだリポジトリで git が改行を変えないようにする(変わるとハッシュが合わなくなる) |

確かめでは、OS が作るファイル(`.DS_Store`・`Thumbs.db`・`desktop.ini`)と Python のキャッシュ(`__pycache__`・`*.pyc`)は見ない。

### アプリのテストに確かめを入れる

Python(電力データ集計。`<置き場所>` を `sys.path` に入れる):

```python
from auth_foundation.verify_vendor import verify

def test_auth_foundation_vendor():
    verify()   # 手で直されていたり、判定テストが通らなければ VendorCheckError
```

JS(SolarOM。Node のテスト):

```js
import { verify } from '<置き場所>/auth_foundation/verify-vendor.mjs';
verify();      // だめなら例外(.problems に一覧)
```

### 使う

```python
from auth_foundation import evaluate, permissions_at, sites_with, check_guard, make_audit_event

d = evaluate(CATALOG, snapshot, user_id, "report.edit", {"type": "site", "id": "A"})
if not d["allowed"]:
    ...  # d["reason"] は not_member / out_of_scope / no_permission。文言はアプリが決める
```

```js
import { evaluate } from './auth_foundation/auth-foundation.mjs';
const d = evaluate(CATALOG, snapshot, userId, 'report.edit', { type: 'site', id: 's001' });
```

- `CATALOG`(機能グループとロール)はアプリのソースに書き、アプリのテストで `validate_catalog(CATALOG) == []` を確かめる
- `snapshot` はアプリのデータベースから作る(形は [spec/vectors.schema.md](spec/vectors.schema.md))
- 監査ログは `make_audit_event(...)` で作ってから、アプリが保存する

**SolarOM の注意**: `デモアプリ/` はまるごと公開される。写し(`vectors/`・`MANIFEST.json` を含む)は `デモアプリ/` の外のサーバー側の置き場所に置き、画面で使うときは `auth-foundation.mjs` だけを `デモアプリ/` の下へ置く。

### 版を上げる

1. このリポジトリで直し、判定テストを足し(監査ログの操作名を変えたら `spec/audit-actions.json` を直して `python3 tools/sync_audit_actions.py` で両方の版へ書き込む)、`VERSION`・`CHANGELOG.md`・両方の版の `VERSION` 定数(`python/auth_foundation/__init__.py`・`js/auth-foundation.mjs`)を上げる(番号の決め方は設計.md §6-1)
2. `tools/check.sh` が通ったらタグ `vX.Y.Z` を付ける
3. 各アプリで、新しいタグを checkout して写し直す(古い写しは手で直されていなければ置き換わる。新しい写しの確かめが通らなければ、古い写しはそのまま残る)

## 判定テストを作り直す

判定テストは `spec/vectors/*.json` が正。生成用のスクリプトが `tools/vectors/` にある。

```sh
python3 tools/vectors/make_generic.py spec/vectors                  # 汎用の決まり(正解は手で書いてある)
python3 tools/vectors/make_pda.py spec/vectors                      # 電力データ集計の今の判定
node tools/vectors/make_solarom.mjs <solar-om のパス> spec/vectors  # SolarOM の perm-data.js を動かして作る
```
