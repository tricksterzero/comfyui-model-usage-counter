# ComfyUI Model Usage Counter

English | [日本語](./README.ja.md)

A minimal ComfyUI custom node that records **how many times each model is used** and **when it was last used**, updating on every generation.

Built on the ComfyUI **V3 node schema**.

## How it works

Drop the **Model Usage Counter** node anywhere on your graph — it needs no input connections. On every run it:

1. Reads the full prompt graph (via the hidden `prompt` input that output nodes receive automatically).
2. Finds the loader nodes that were actually used and extracts their model names.
3. Increments a per-model counter and records the last-used timestamp, then writes them to `model_usage.json`.
4. Displays the current totals on the node.

Because it has no outputs, it never triggers recomputation of downstream nodes (KSampler, etc.). A `fingerprint_inputs()` returning the current time forces the node to run on every generation, so counts increment even when the same model is reused.

### Tracked loaders

| `class_type`            | model name key | bucket      |
| ----------------------- | -------------- | ----------- |
| `CheckpointLoaderSimple`| `ckpt_name`    | checkpoint  |
| `UNETLoader`            | `unet_name`    | unet        |

To track more loader types, add a line to `LOADER_KEYS` in `__init__.py`.

## Output format

`model_usage.json` (stored in the ComfyUI user/output directory, **not** inside this repo):

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

`last_used` is an ISO 8601 timestamp in local time (with UTC offset).

## Installation

Clone into your `custom_nodes` directory and restart ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/<your-username>/comfyui-model-usage-counter
```

Or install via ComfyUI-Manager ("Install via Git URL").

## Requirements

- A ComfyUI version that supports the V3 node schema (`comfy_api.latest`).
- No extra Python dependencies (standard library only).

## Notes / limitations

- LoRA counting is not implemented. The structure is ready for it; loaders that bundle multiple LoRAs (e.g. rgthree Power Lora Loader) need dedicated parsing in `extract_models()`.
- With `batch_count > 1`, the count increases by the number of images generated (usage is counted per image, not per workflow run).
- If multiple Model Usage Counter nodes are placed in one graph, counting is performed only once (by the node with the smallest node id), so totals are never inflated by node count.
- Duplicate loaders within a single graph are each counted, reflecting actual usage.

## License

MIT
