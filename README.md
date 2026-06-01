# ComfyUI Model Usage Counter

English | [日本語](./README.ja.md)

A ComfyUI custom node that automatically records **how many times each model is used**
and **when it was last used**. Just drop it on your graph and the counts grow with every
generation.

Handy for answering questions like "which checkpoint have I been using lately?" or
"which models am I no longer using?"

## Features

- **Just drop it in** — place one node on your graph; no wiring (input connections) needed.
- **Automatic counting** — records the models actually used on every generation.
- **Per-type totals** — counts checkpoints, diffusion models (unet), and LoRAs separately.
- **Last-used timestamp** — see when each model was last used.
- **Shown on the node** — the current totals are displayed on the node after each generation.
- **Saved as JSON** — data is written to `model_usage.json` for use by other tools.
- **No extra dependencies** — standard library only.

## Installation

Clone into your `custom_nodes` directory and restart ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/tricksterzero/comfyui-model-usage-counter
```

Or install via ComfyUI-Manager ("Install via Git URL").

## Usage

1. Add **Model Usage Counter** from the **utils/stats** category (node search or menu).
2. Place it anywhere on your graph (it doesn't need to be connected to anything).
3. Generate as usual (Queue Prompt).
4. The models you used are written to `model_usage.json`, and the current totals are shown on the node.

The node displays something like this (it appears after one generation):

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

Each bucket starts with a header row — **使用回数** (count) / **最終使用日時** (last used) /
**経過** (elapsed) / **モデル名** (model). Entries are ordered by **most recently used
first**, and columns are width-aware (full-width-safe) aligned. The elapsed label is in
Japanese: `たった今` (just now), `n分前` (n minutes ago), `n時間前` (hours), `n日前` (days),
`nヶ月前` (months), `n年前` (years).

## Recorded data

Data is saved to `model_usage.json`. It lives in a `model-usage-counter/` folder inside
ComfyUI's user directory — **not** inside this repository — so it survives updates and
reinstalls. (The output directory is deliberately avoided since it can be served over HTTP.)

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

- `count` … number of times the model was used
- `last_used` … when it was last used (local time, ISO 8601 with UTC offset)

## Tracked models

These loaders are currently counted:

| Loader                              | bucket       |
| ----------------------------------- | ------------ |
| `CheckpointLoaderSimple`            | checkpoint   |
| `UNETLoader`                        | unet         |
| `LoraLoader` (Load LoRA)            | lora         |
| `LoraLoaderModelOnly` (Load LoRA)   | lora         |
| `LoraLoader\|pysssss` (Custom-Scripts) | lora      |
| `Power Lora Loader (rgthree)`       | lora         |
| `Lora Loader (LoraManager)`         | lora         |

For loaders that bundle multiple LoRAs (rgthree **Power Lora Loader**, **Lora Loader
(LoraManager)**), only the **enabled/active** entries are counted, each recorded separately.
All LoRAs are grouped together under the `lora` bucket regardless of which loader they came
from. To track other simple loaders, add a line to `LOADER_KEYS` in `__init__.py` (see "How
it works" below).

## Limitations

- **With `batch_count > 1`**, the count increases by the number of images generated
  (usage is counted per image, not per workflow run).
- Placing **multiple Model Usage Counter nodes** in one graph still counts **only once**
  (totals are never inflated by node count).
- Duplicate loaders within a single graph are each counted, reflecting actual usage.

## How it works

<details>
<summary>Technical details (click to expand)</summary>

Built on ComfyUI's **V3 node schema** (`comfy_api.latest`).

This is an output node with no output ports. On every generation it:

1. Reads the full prompt graph (via the hidden `prompt` input that output nodes receive
   automatically).
2. Finds the loader nodes that were actually used and extracts their model names.
3. Increments a per-model counter, records the last-used timestamp, and writes them to
   `model_usage.json`.
4. Returns the totals as text, which the bundled JS extension renders on the node.

Because it has no outputs, it never triggers recomputation of downstream nodes (KSampler,
etc.). A `fingerprint_inputs()` returning the current time forces the node to run on every
generation, so counts increment even when the same model is reused.

The on-node display works by returning `ui.PreviewText` from `execute()` (delivered as
`message.text` in the `executed` event) and rendering it into a read-only multiline widget
via the bundled JS extension (`js/model_usage_counter.js`, served through `WEB_DIRECTORY`).

Simple loaders are defined in `LOADER_KEYS` in `__init__.py`. Add a line in the form
`class_type -> (model name key, bucket, folder_paths folder)` to track more. The third item
is the `folder_paths` category used to verify the model exists: only names present in
`folder_paths.get_filename_list(...)` are recorded, so arbitrary strings in a submitted
prompt can't bloat `model_usage.json`. Confirm the `class_type` and inputs key from the
prompt metadata of an actual output PNG, and the folder name from the loader's `INPUT_TYPES`.

Loaders that bundle multiple models in a non-trivial input structure are handled by
dedicated branches in `extract_models()`:

- rgthree **Power Lora Loader** — `inputs` hold many `lora_N` entries of the form
  `{"on": bool, "lora": "name", "strength": float, ...}` (`_extract_power_loras`).
- **Lora Loader (LoraManager)** — `inputs["loras"]` holds a list (`{"__value__": [...]}` or a
  plain list) of `{"name", "active", "strength", ...}`; active entries are resolved to the
  real `folder_paths` filename, since the stored name may omit the extension or subfolder
  (`_extract_loramanager_loras` + `_resolve_lora_name`).

Adding another such loader means writing a similar branch.

</details>

## Requirements

- A ComfyUI version that supports the V3 node schema (`comfy_api.latest`).
- No extra Python dependencies (standard library only).

## License

MIT
