# CLAUDE.md

ComfyUI の V3 ノードスキーマで作られたモデル使用回数カウンタ。将来のセッションで
この README 的把握を毎回やり直さずに済むよう、設計意図・拡張手順・落とし穴をまとめる。

## プロジェクト概要

- ComfyUI V3 スキーマ（`comfy_api.latest`）のカスタムノード `ModelUsageCounter`。
- 生成のたびにグラフ内ローダーが使用したモデル名を抽出し、**使用回数**と
  **最終使用日時**を `model_usage.json` に記録する。
- グラフ上に置くだけで動作（入力接続不要）。

## アーキテクチャ（なぜこの設計か）

- Python 実装は **`__init__.py` 単一ファイル**に集約。依存は Python 標準ライブラリのみ
  （＋ ComfyUI の `comfy_api.latest` / `folder_paths`）。
- **ノード上表示は JS 拡張で行う**（`js/model_usage_counter.js`、`WEB_DIRECTORY="./js"` で配信）。
  バックエンドは `execute()` で `ui.PreviewText(text)` を返し、生成完了時の `"executed"`
  イベントで `message.text` を送る。JS 側はそれを読み取り専用の複数行ウィジェットに描画する。
  コア側の text 表示はフロントのバージョン依存で不確実なため、自前ウィジェットで確実に表示する。
  対象は `nodeData.name === "MUC_ModelUsageCounter"` で判定（= `ModelUsageCounter.NODE_ID`）。
- **末端ノードとして毎回確実に実行させる仕組み**:
  - `is_output_node=True`（末端ノード化）
  - `not_idempotent=True`（キャッシュ出力を再利用しない）
  - `fingerprint_inputs()` が `time.time()` を返す（毎回ユニーク値でキャッシュ無効化）。
    → 同じモデルで連続生成してもカウントが必ず増える。
- **`outputs=[]` は重要**: 出力が無いため下流ノード（KSampler 等）の再計算を誘発しない。
  この性質を壊さないこと（出力を足すと毎生成で下流が再計算される）。
- **prompt 走査方式**: hidden の `prompt`（グラフ全体の API 形式 dict）を
  `extract_models()` で走査してモデル名を取得する。ローダー側に出力ポートを足す必要がなく、
  実際に使われたモデルと記録が必ず一致する。
- `fingerprint_inputs()` の戻り値は **JSON シリアライズ可能**でなければならない
  （メタデータ書き出しで失敗するため float を返している）。

## 対象ローダーの拡張手順

`__init__.py` の `LOADER_KEYS` に `class_type -> (inputsキー, 種別ラベル, 実在チェック用フォルダ名)`
を1行足すだけ。3番目は `folder_paths.get_filename_list(...)` に渡すフォルダ名で、`extract_models()`
が**実在するモデル名のみ記録**するために使う（任意文字列による `model_usage.json` 肥大化を防ぐ）。

```python
LOADER_KEYS = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoint", "checkpoints"),
    "UNETLoader":             ("unet_name", "unet", "diffusion_models"),
    # 例) "UnetLoaderGGUF":   ("unet_name", "unet", "diffusion_models"),
}
```

- 追加するローダーの `class_type` 名・inputs キー・フォルダ名は拡張実装に依存する。
  class_type と inputs キーは実機の出力 PNG メタデータ（prompt）で、フォルダ名は対象拡張の
  `INPUT_TYPES`（`folder_paths.get_filename_list("...")`）で確認してから追加すること。
- フォルダ名が間違っていると実在チェックで弾かれ**何も記録されなくなる**点に注意。

### 特殊構造ローダー（複数モデルをまとめるタイプ）

inputs がモデル名1個＝キー1個の単純形でないローダーは `LOADER_KEYS` では拾えない。
`extract_models()` 内に専用分岐を足す。現状は rgthree **Power Lora Loader** に対応済み。

- class_type は `Power Lora Loader (rgthree)`（rgthree の `get_name()` が NAMESPACE を付ける）。
  inputs は `lora_1`, `lora_2`, ... のキーごとに
  `{"on": bool, "lora": "名前.safetensors", "strength": float, "strengthTwo": float(任意)}`。
- 抽出は `_extract_power_loras()`。**キーが `lora_` で始まり `on` が真**の項目だけを
  種別 `lora`（フォルダ `loras`）として記録。`model` / `clip` 等の接続キーは無視する。
- **`on` のみで判定**し strength=0 は除外しない（rgthree 自身の
  `get_enabled_loras_from_prompt_node` も `on` のみを見るため、それに合わせた）。
- 他ローダーと同様 `folder_paths.get_filename_list("loras")` との**完全一致のみ記録**
  （肥大化防止）。rgthree はファジーマッチもするが、UI はファイル一覧から選んで widget に
  格納するため prompt 値は通常 canonical 名と一致する。一致しなければ記録しない（安全側）。
- 別の同種ローダーを足す場合はこれに倣った分岐を新設する。

## 実装上の注意（落とし穴）

- **多重加算対策**: 同一グラフに複数のカウンタを置くと各ノードがグラフ全体を走査するため、
  対策しないと設置個数分だけ多重加算される。`execute()` の `is_primary` 判定により
  **最小 node_id を持つ1つだけ**が加算する。表示（PreviewText）は全ノードで行ってよい。
  この判定ロジックを壊さないこと。
- **保存先はリポジトリ外**: `folder_paths.get_user_directory()` 直下の
  `model-usage-counter/model_usage.json`、取得不可ならノードフォルダ直下にフォールバック。
  利用者の git pull / 再インストールでデータが消えたりリポジトリを汚したりしないための方針。
  セキュリティ上、**output ディレクトリは使わない**（`/view` で Web 配信され集計データが
  露出し得るため）。user ディレクトリ直下は `/userdata`（`user/{user_id}/` 配下）の対象外で
  安全。この方針を維持すること。
- **データ形式**: `{"count": int, "last_used": isoformat}`。旧形式（int 値）も読めるよう
  後方互換の読み出しを保持している（`isinstance(rec, dict)` 分岐）。崩さないこと。
- **batch 仕様**: `batch_count > 1` のときは画像枚数分カウントされる（ワークフロー実行単位ではない）。

## 未対応 / 既知の制限

- **LoRA カウントは rgthree Power Lora Loader のみ対応**（上記「特殊構造ローダー」参照）。
  それ以外の LoRA ローダー（標準 `LoraLoader` 等）は未対応。標準 LoraLoader は inputs が
  単純（`lora_name` キー）なので `LOADER_KEYS` に1行足せば対応できるはず（class_type と
  キーは実機の prompt で要確認）。他の集約型ローダーは個別分岐を追加する。
- `pyproject.toml` に未設定のプレースホルダが残存（公開前に要設定）:
  - `PublisherId = "<your-publisher-id>"`
  - `requires-comfyui`（コメントアウト。動作確認した下限バージョンを設定する）
- **セキュリティ指摘5（クロスプロセスのロック）は意図的に見送り**。`_lock` は `threading.Lock`
  でプロセス内のみ。共有 user ディレクトリで複数 ComfyUI を動かすと同時更新時にカウント
  取りこぼしの可能性があるが、指摘4のアトミック書き込みで「壊れた中間状態の読み取り」は
  解消済み。通常は単一プロセス運用のため対処コスト過大と判断。必要になれば OS 依存の
  ファイルロックで対応する。

## 持ち越しタスク（公開準備）

機能追加の区切りがついた時点で、以下をまとめて対応する方針:

- `pyproject.toml` の `PublisherId` / `requires-comfyui` を設定（上記「未対応」参照）。
- **バージョンは `1.0.0` のまま確定**する（公開準備と同時に。それまで途中で上げない）。
- これらが整ったら Comfy Registry へ公開可能になる。

## ドキュメント運用

- 機能を変更したら `README.md`（英語）と `README.ja.md`（日本語）の**両方**を更新する。
  両ファイルは構成・内容を揃える。
- **README は利用者（エンドユーザー）向けに書く**。冒頭は「何ができるか・どう使うか」を中心にし、
  内部実装の解説（V3 スキーマ、`fingerprint_inputs`、`prompt` 走査、`LOADER_KEYS` 拡張 等の
  技術詳細）は末尾の「仕組み」セクションに `<details>` で折りたたんでまとめる。
- コメント・ドキュメント（README 等）は日本語で記述する。
- **コミットは必ず事前に利用者へ確認を取ってから行う**。勝手にコミットしない。
  変更内容を提示し、コミットしてよいか確認を取ってから `git commit` を実行すること
  （コミットメッセージ案も提示してよいが、実行は承認後）。
- **コミットメッセージは英語**で書く（GitHub のページ上で最初に見える範囲を英語にしておきたいため）。
  Conventional Commits の prefix（feat / docs / fix など）＋簡潔な1行の件名を基本とし、
  各コミットに `Co-Authored-By` トレーラを付与する。
