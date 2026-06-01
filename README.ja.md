# ComfyUI Model Usage Counter

[English](./README.md) | 日本語

**どのモデルを何回使ったか・いつ最後に使ったか**を自動で記録する ComfyUI カスタムノードです。
グラフに置くだけで、生成のたびにカウントが増えていきます。

「最近どのチェックポイントをよく使っているか」「もう使っていないモデルはどれか」を
あとから振り返るのに役立ちます。

## 特徴

- **置くだけ** — ノードをグラフに1つ置くだけ。配線（入力の接続）は不要です。
- **自動カウント** — 生成のたびに、実際に使われたモデルを自動で記録します。
- **種別ごとに集計** — checkpoint・diffusion model (unet)・LoRA を分けて数えます。
- **最終使用日時も記録** — いつ最後に使ったかが分かります。
- **ノード上に一覧表示** — 生成のたびに、現在の集計をノード上で確認できます。
- **JSON で保存** — データは `model_usage.json` に保存され、他のツールでも扱えます。
- **追加依存なし** — Python 標準ライブラリのみで動作します。

## インストール

`custom_nodes` ディレクトリに clone して ComfyUI を再起動します。

```
cd ComfyUI/custom_nodes
git clone https://github.com/tricksterzero/comfyui-model-usage-counter
```

または ComfyUI-Manager の「Install via Git URL」から導入できます。

## 使い方

1. ノード検索やメニューの **utils/stats** カテゴリから **Model Usage Counter** を追加します。
2. グラフ上のどこかに置きます（何も繋がなくて構いません）。
3. いつも通り生成（Queue Prompt）します。
4. 使用したモデルが `model_usage.json` に記録され、ノード上にも現在の集計が表示されます。

ノード上にはこのように表示されます（生成を1回行うと現れます）。

```
[checkpoint]
  使用回数  最終使用日時             経過  モデル名
        12  2026-06-01 17:30:00  たった今  someCheckpoint.safetensors
         4  2026-05-30 09:10:00     2日前  olderCheckpoint.safetensors
[lora]
  使用回数  最終使用日時            経過  モデル名
        18  2026-06-01 17:29:30  たった今  detailTweaker.safetensors
         5  2026-05-28 11:00:00     4日前  char/someCharacter.safetensors
[unet]
  使用回数  最終使用日時            経過  モデル名
        30  2026-06-01 15:18:42  2時間前  someDiffusionModel.safetensors
         8  2026-03-21 22:05:00  2ヶ月前  anotherUnet.safetensors
```

各種別ブロックの先頭に列ヘッダ（**使用回数 / 最終使用日時 / 経過 / モデル名**）が付きます。
ブロック内は**最終使用日時の新しい順**に並び、経過は `たった今` / `n分前` / `n時間前` /
`n日前` / `nヶ月前` / `n年前` で表示されます（全角を考慮して桁揃えされます）。

## 記録されるデータ

データは `model_usage.json` に保存されます。**このリポジトリ内ではなく**、ComfyUI の
user ディレクトリ内の `model-usage-counter/` フォルダに保存されるため、アップデートや
再インストールで消えることはありません。（output ディレクトリは HTTP 配信され得るため
保存先には使いません。）

```json
{
  "checkpoint": {
    "someCheckpoint.safetensors": { "count": 12, "last_used": "2026-06-01T14:30:00+09:00" }
  },
  "unet": {
    "someDiffusionModel.safetensors": { "count": 30, "last_used": "2026-06-01T15:02:11+09:00" }
  },
  "lora": {
    "detailTweaker.safetensors": { "count": 18, "last_used": "2026-06-01T17:29:30+09:00" }
  }
}
```

- `count` … そのモデルを使った回数
- `last_used` … 最後に使った日時（ローカル時刻、UTCオフセット付きの ISO 8601 形式）

## 対象モデル

現在カウントできるのは次のローダーです。

| ローダー                            | 集計種別     |
| ----------------------------------- | ------------ |
| `CheckpointLoaderSimple`            | checkpoint   |
| `UNETLoader`                        | unet         |
| `LoraLoader`（Load LoRA）           | lora         |
| `LoraLoaderModelOnly`（Load LoRA）  | lora         |
| `LoraLoader\|pysssss`（Custom-Scripts） | lora      |
| `Power Lora Loader (rgthree)`       | lora         |
| `Lora Loader (LoraManager)`         | lora         |

複数の LoRA をまとめるローダー（rgthree **Power Lora Loader**、**Lora Loader
(LoraManager)**）では、**有効（ON / active）な項目だけ**をそれぞれ個別に数えます。
どのローダー由来でも、LoRA はすべて `lora` 種別にまとめて集計します。ほかの単純なローダーに
対応させたい場合は、`__init__.py` の `LOADER_KEYS` に1行追加します（詳しくは下記「仕組み」を参照）。

## 制限事項

- **`batch_count > 1` のとき**は、生成枚数の分だけカウントが増えます（ワークフローの実行回数ではなく、
  画像1枚ごとに数えます）。
- 1つのグラフに Model Usage Counter を**複数置いても、加算は1回だけ**です（設置個数で
  多重に数えられることはありません）。
- 1つのグラフに同じローダーが複数ある場合は、それぞれ数えられます（実際の使用状況を反映）。

## 仕組み

<details>
<summary>技術的な詳細（クリックで展開）</summary>

ComfyUI の **V3 ノードスキーマ**（`comfy_api.latest`）で実装しています。

このノードは出力ポートを持たない末端ノード（output node）で、生成のたびに次を行います。

1. 出力ノードが自動的に受け取る隠し入力 `prompt`（グラフ全体）を読み取る
2. 実際に使われたローダーノードを見つけ、モデル名を抽出する
3. モデルごとのカウンタを加算し、最終使用日時を記録して `model_usage.json` に書き込む
4. 集計テキストを返し、同梱の JS 拡張がノード上に描画する

出力ポートを持たないため、下流ノード（KSampler など）の再計算は引き起こしません。
`fingerprint_inputs()` が現在時刻を返すことでノードは毎回実行され、同じモデルを使い回しても
確実にカウントが加算されます。

ノード上の表示は、`execute()` が返す `ui.PreviewText`（生成完了時の `executed` イベントの
`message.text`）を、同梱の JS 拡張（`js/model_usage_counter.js`、`WEB_DIRECTORY` で配信）が
読み取り専用の複数行テキスト欄に描画することで実現しています。

単純なローダーは `__init__.py` の `LOADER_KEYS` で定義しています。
`class_type -> (モデル名のキー, 集計種別, 実在チェック用フォルダ名)` の形式で1行追加すれば
対応を増やせます。3番目は `folder_paths.get_filename_list(...)` に渡すフォルダ名で、実在する
モデル名のみを記録するために使います（投稿された prompt 内の任意文字列で `model_usage.json` が
肥大化するのを防ぎます）。追加するローダーの `class_type` 名や inputs のキーは、実機の出力 PNG メタデータ（prompt）で
一度確認してください。

複数のモデルを特殊な inputs 構造にまとめるローダーは、`extract_models()` 内の専用分岐で処理します。

- rgthree **Power Lora Loader** — `inputs` が `{"on": bool, "lora": "名前", "strength": float, ...}`
  形式の `lora_N` 項目を多数持つ（`_extract_power_loras`）。
- **Lora Loader (LoraManager)** — `inputs["loras"]` が `{"name", "active", "strength", ...}` の
  リスト（`{"__value__": [...]}` か素のリスト）。active な項目を、格納名が拡張子やサブフォルダを
  省く場合があるため実在する `folder_paths` のファイル名へ解決して記録する
  （`_extract_loramanager_loras` ＋ `_resolve_lora_name`）。

同様のローダーを増やす場合は、これに倣った分岐を書きます。

</details>

## 動作要件

- V3 ノードスキーマ（`comfy_api.latest`）に対応した ComfyUI
- 追加の Python 依存パッケージは不要（標準ライブラリのみ）

## ライセンス

MIT
