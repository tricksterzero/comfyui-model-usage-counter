# ComfyUI Model Usage Counter

[English](./README.md) | 日本語

生成のたびに **各モデルの使用回数** と **最終使用日時** を記録・更新するミニマルな ComfyUI カスタムノードです。ComfyUI の **V3 ノードスキーマ**で実装しています。

## 動作の仕組み

**Model Usage Counter** ノードをグラフ上のどこかに置くだけで動作します(入力の接続は不要)。生成のたびに以下を行います。

1. グラフ全体のプロンプトを読み取る(出力ノードが自動的に受け取る隠し入力 `prompt` を利用)
2. 実際に使われたローダーノードを見つけ、モデル名を抽出する
3. モデルごとのカウンタを加算し、最終使用日時を記録して `model_usage.json` に書き込む
4. 現在の集計をノード上に表示する

出力ポートを持たないため、下流ノード(KSampler など)の再計算を引き起こしません。`fingerprint_inputs()` が現在時刻を返すことでノードは毎回実行され、同じモデルを使い回しても確実にカウントが加算されます。

### 対象ローダー

| `class_type`             | モデル名のキー  | 集計種別     |
| ------------------------ | --------------- | ------------ |
| `CheckpointLoaderSimple` | `ckpt_name`     | checkpoint   |
| `UNETLoader`             | `unet_name`     | unet         |

対象を増やしたい場合は `__init__.py` の `LOADER_KEYS` に1行追加してください。

## 出力形式

`model_usage.json`(このリポジトリ内ではなく、ComfyUI の user / output ディレクトリに保存されます):

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

`last_used` はローカル時刻(UTCオフセット付き)の ISO 8601 形式です。

## インストール

`custom_nodes` ディレクトリに clone して ComfyUI を再起動します。

```
cd ComfyUI/custom_nodes
git clone https://github.com/<your-username>/comfyui-model-usage-counter
```

または ComfyUI-Manager の「Install via Git URL」から導入できます。

## 動作要件

- V3 ノードスキーマ(`comfy_api.latest`)に対応した ComfyUI
- 追加の Python 依存パッケージは不要(標準ライブラリのみ)

## 備考・制限事項

- LoRA のカウントは未実装です。構造上は追加可能ですが、複数の LoRA をまとめて扱うローダー(例: rgthree Power Lora Loader)は `extract_models()` に専用の解析を足す必要があります。
- `batch_count > 1` のときは、生成枚数の分だけカウントが増えます(ワークフローの実行回数ではなく、画像1枚ごとに数えます)。
- 1つのグラフ内に Model Usage Counter を複数置いた場合でも、加算は1回だけ行われます(最小の node id を持つノードが代表して記録するため、設置個数で多重加算されません)。
- 1つのグラフ内に同じローダーが複数ある場合はそれぞれ数えられ、実際の使用状況を反映します。

## ライセンス

MIT