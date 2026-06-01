# ComfyUI Model Usage Counter

[English](./README.md) | 日本語

生成のたびに **各モデルの使用回数を記録・加算する** ミニマルな ComfyUI カスタムノードです。ComfyUI の **V3 ノードスキーマ**で実装しています。

## 動作の仕組み

**Model Usage Counter** ノードをグラフ上のどこかに置くだけで動作します(入力の接続は不要)。生成のたびに以下を行います。

1. グラフ全体のプロンプトを読み取る(出力ノードが自動的に受け取る隠し入力 `prompt` を利用)
2. 実際に使われたローダーノードを見つけ、モデル名を抽出する
3. モデルごとのカウンタを加算し、`model_usage.json` に書き込む
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
  "checkpoint": { "someCheckpoint.safetensors": 12 },
  "unet": { "someDiffusionModel.safetensors": 30 }
}
```

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
- `batch_count > 1` のときの挙動(各反復でカウントが加算されるか)は未検証です。各自の環境で確認してください。
- 1つのグラフ内に同じローダーが複数ある場合はそれぞれ数えられ、実際の使用状況を反映します。

## ライセンス

MIT