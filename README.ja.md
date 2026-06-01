# ComfyUI Model Usage Counter

[English](./README.md) | 日本語

**どのモデルを何回使ったか・いつ最後に使ったか**を自動で記録する ComfyUI カスタムノードです。
グラフに置くだけで、生成のたびにカウントが増えていきます。

「最近どのチェックポイントをよく使っているか」「もう使っていないモデルはどれか」を
あとから振り返るのに役立ちます。

## 特徴

- **置くだけ** — ノードをグラフに1つ置くだけ。配線（入力の接続）は不要です。
- **自動カウント** — 生成のたびに、実際に使われたモデルを自動で記録します。
- **種別ごとに集計** — checkpoint と diffusion model (unet) を分けて数えます。
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
     12  2026-06-01 17:14:35 (たった今)  someCheckpoint.safetensors
      4  2026-05-30 09:10:00 (2日前)     olderCheckpoint.safetensors
[unet]
     30  2026-06-01 15:02:11 (2時間前)   someDiffusionModel.safetensors
```

各ブロック内は**最終使用日時の新しい順**に並び、日時は「絶対表記（`YYYY-MM-DD HH:MM:SS`）＋
相対表記（`たった今` / `n分前` / `n時間前` / `n日前` / `nヶ月前` / `n年前`）」で表示されます。

## 記録されるデータ

データは `model_usage.json` に保存されます。**このリポジトリ内ではなく**、ComfyUI の
user / output ディレクトリ内の `model-usage-counter/` フォルダに保存されるため、
アップデートや再インストールで消えることはありません。

```json
{
  "checkpoint": {
    "someCheckpoint.safetensors": { "count": 12, "last_used": "2026-06-01T14:30:00+09:00" }
  },
  "unet": {
    "someDiffusionModel.safetensors": { "count": 30, "last_used": "2026-06-01T15:02:11+09:00" }
  }
}
```

- `count` … そのモデルを使った回数
- `last_used` … 最後に使った日時（ローカル時刻、UTCオフセット付きの ISO 8601 形式）

## 対象モデル

現在カウントできるのは次のローダーです。

| ローダー                 | 集計種別     |
| ------------------------ | ------------ |
| `CheckpointLoaderSimple` | checkpoint   |
| `UNETLoader`             | unet         |

ほかのローダーにも対応させたい場合は、`__init__.py` の `LOADER_KEYS` に1行追加します
（詳しくは下記「仕組み」を参照）。

## 制限事項

- **LoRA は未対応** です。特に複数の LoRA をまとめて扱うローダー（例: rgthree Power Lora Loader）は
  別途対応が必要です。
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

対象ローダーは `__init__.py` の `LOADER_KEYS` で定義しています。
`class_type -> (モデル名のキー, 集計種別)` の形式で1行追加すれば対応を増やせます。
追加するローダーの `class_type` 名や inputs のキーは、実機の出力 PNG メタデータ（prompt）で
一度確認してください。

</details>

## 動作要件

- V3 ノードスキーマ（`comfy_api.latest`）に対応した ComfyUI
- 追加の Python 依存パッケージは不要（標準ライブラリのみ）

## ライセンス

MIT
