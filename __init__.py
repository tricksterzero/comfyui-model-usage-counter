# ComfyUI custom node: Model Usage Counter (V3 schema)
# 生成毎に、グラフ内で実際に使われたローダーのモデル名を抽出してカウントを記録する。
#
# 設計の要点:
#   - 入力ポートを持たず、is_output_node=True により末端ノードとして必ず実行される。
#     output node には prompt / extra_pnginfo が自動的に渡される(V3仕様)。
#   - fingerprint_inputs() が毎回 time.time() を返すため、同じモデルで連続生成しても
#     キャッシュされず必ず再実行される(= 確実にカウントが増える)。
#   - outputs=[] なので、毎回実行されても下流ノード(KSampler等)の再計算を誘発しない。
#   - cls.hidden.prompt(グラフ全体のAPI形式dict)を自分で走査してモデル名を取得するため、
#     ローダー側に出力ポートを足す必要がない。実際に使われたモデルと記録が必ず一致する。

import time
import json
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from comfy_api.latest import ComfyExtension, io, ui

try:
    import folder_paths  # ComfyUI標準。custom_nodeロード時には利用可能。
except ImportError:
    folder_paths = None

# ----------------------------------------------------------------------------
# カウント対象ローダーの定義
#   class_type -> (モデル名が入る inputs のキー, 集計上の種別ラベル)
#
# 後から種類を増やしたい場合はここに1行足すだけ。
#   例) "ImageOnlyCheckpointLoader": ("ckpt_name", "checkpoint")
#       "UnetLoaderGGUF":            ("unet_name", "unet")   # GGUFを使う場合
#
# 注意(未確認): 追加するローダーの class_type 名やキー名は拡張の実装に依存する。
#   実機の出力PNGメタデータ(prompt)で class_type と inputs のキーを一度確認すること。
# 注意: rgthree Power Lora Loader 等の LoRA は inputs 構造が特殊(複数LoRAを内部にまとめる)で、
#   下の単純なキー抽出では拾えない。LoRA対応は extract_models() 内に専用分岐を足す形になる。
# ----------------------------------------------------------------------------
LOADER_KEYS = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoint"),
    "UNETLoader":             ("unet_name", "unet"),
}

# ----------------------------------------------------------------------------
# ノード表示に使う文言。将来の多言語化に備えてここに集約し、ロジック中に
# 日本語を直接ハードコードしない。相対表記の {n} は経過数値で置換する。
# ----------------------------------------------------------------------------
DISPLAY_TEXT = {
    # 列ヘッダ
    "col_count":   "使用回数",
    "col_updated": "最終使用日時",
    "col_elapsed": "経過",
    "col_model":   "モデル名",
    # 相対表記(経過時間)
    "rel_now":     "たった今",
    "rel_minutes": "{n}分前",
    "rel_hours":   "{n}時間前",
    "rel_days":    "{n}日前",
    "rel_months":  "{n}ヶ月前",
    "rel_years":   "{n}年前",
    # その他
    "empty":       "-",
    "no_loaders":  "(対象ローダーが見つかりませんでした)",
}

# 集計ファイルの保存先。
#   公開ノードでは、利用者の git pull / 再インストールでデータが消えたり
#   リポジトリを汚したりしないよう、ノードフォルダの外に保存する。
#   user ディレクトリ → output ディレクトリ → (最終手段)ノードフォルダ直下、の順で試す。
_lock = threading.Lock()


def _count_file() -> Path:
    base = None
    if folder_paths is not None:
        # get_user_directory は存在しないバージョンもあり得るため try で吸収する(未確認)。
        for getter in ("get_user_directory", "get_output_directory"):
            fn = getattr(folder_paths, getter, None)
            if callable(fn):
                try:
                    base = Path(fn())
                    break
                except Exception:
                    continue
    if base is None:
        base = Path(__file__).parent
    data_dir = base / "model-usage-counter"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "model_usage.json"


def _load_counts() -> dict:
    path = _count_file()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_counts(data: dict) -> None:
    _count_file().write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def extract_models(prompt: dict) -> list[tuple[str, str]]:
    """prompt(API形式 dict)を走査し、(種別, モデル名) のリストを返す。

    prompt の形は {node_id: {"class_type": str, "inputs": {...}}, ...}。
    同じローダーが複数あればその数だけ拾う(= 実際に使った回数)。
    """
    found = []
    if not isinstance(prompt, dict):
        return found
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        spec = LOADER_KEYS.get(ct)
        if spec is None:
            continue
        key, mtype = spec
        name = node.get("inputs", {}).get(key)
        if isinstance(name, str) and name:
            found.append((mtype, name))
    return found


def _humanize_delta(seconds: float) -> str:
    """現在時刻との差(秒)を相対表記に変換する。差が負(未来)なら『たった今』に丸める。"""
    t = DISPLAY_TEXT
    if seconds < 60:            # 60秒未満(負=未来日時もここに含めて丸める)
        return t["rel_now"]
    if seconds < 3600:         # 60分未満
        return t["rel_minutes"].format(n=int(seconds // 60))
    if seconds < 86400:        # 24時間未満
        return t["rel_hours"].format(n=int(seconds // 3600))
    days = int(seconds // 86400)
    if days < 30:              # 30日未満
        return t["rel_days"].format(n=days)
    if days < 365:             # 365日未満(30日=1ヶ月として概算)
        return t["rel_months"].format(n=days // 30)
    return t["rel_years"].format(n=days // 365)  # 365日以上(365日=1年として概算)


def _format_last_used_parts(iso: str, now=None) -> tuple[str, str]:
    """TZ付きISO 8601文字列を (絶対表記, 相対表記) に分解する。

    絶対表記は 'YYYY-MM-DD HH:MM:SS'("T"を空白に・TZオフセット除去した形、strftimeで等価)。
    相対表記は表示生成時の現在時刻を基準に、aware 同士の差分で算出する。
    パースできない文字列は (元文字列, "") を返す。
    """
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso, ""
    absolute = dt.strftime("%Y-%m-%d %H:%M:%S")
    if now is None:
        now = datetime.now().astimezone()
    if dt.tzinfo is None:                         # naive なら端末TZで aware 化して揃える
        dt = dt.astimezone()
    seconds = (now - dt).total_seconds()
    return absolute, _humanize_delta(seconds)


def _disp_width(s: str) -> int:
    """等幅フォント上の表示幅を返す。全角(east_asian_width が F/W/A)=2、他=1 で数える。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W", "A") else 1 for c in s)


def _pad(s: str, width: int, right: bool = False) -> str:
    """表示幅 width に揃えて半角空白でパディングする(全角を2幅として計算)。"""
    gap = " " * max(0, width - _disp_width(s))
    return gap + s if right else s + gap


class ModelUsageCounter(io.ComfyNode):
    NODE_ID = "MUC_ModelUsageCounter"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=cls.NODE_ID,
            display_name="Model Usage Counter",
            category="utils/stats",
            description=(
                "生成毎に、グラフ内のローダーが使用したモデル名を種別ごとにカウントして "
                "model_usage.json に記録する。ノードに何も繋がず、グラフ上に置くだけで動作する。"
            ),
            inputs=[],                 # 入力なし(prompt は hidden で取得)
            outputs=[],                # 出力なし → 下流の再計算を誘発しない
            # prompt: グラフ全体の走査用 / unique_id: 複数設置時の重複加算防止用
            hidden=[io.Hidden.prompt, io.Hidden.unique_id],
            is_output_node=True,       # 末端ノードとして毎回実行される
            not_idempotent=True,       # キャッシュ出力を再利用しない
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        # 毎回ユニークな値(float)を返してキャッシュを無効化する。
        # JSONシリアライズ可能でなければメタデータ書き出しで失敗するため float を返す。
        return time.time()

    @classmethod
    def execute(cls) -> io.NodeOutput:
        prompt = cls.hidden.prompt
        my_id = cls.hidden.unique_id

        # 同一グラフに複数の Model Usage Counter が置かれた場合、各ノードが
        # それぞれグラフ全体を走査するため、対策しないと設置個数分だけ多重加算される。
        # そこで、グラフ内のカウンタノードのうち最小 node_id を持つ1つだけが加算を行う。
        # (node_id は文字列で来る場合があるため、数値化できれば数値で、できなければ
        #  文字列のまま比較してフォールバックする。)
        counter_ids = [
            nid for nid, node in (prompt or {}).items()
            if isinstance(node, dict) and node.get("class_type") == cls.NODE_ID
        ]

        def _key(v):
            s = str(v)
            return (0, int(s)) if s.lstrip("-").isdigit() else (1, s)

        is_primary = (not counter_ids) or (str(my_id) == min(counter_ids, key=_key))

        if is_primary:
            models = extract_models(prompt)
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            with _lock:
                data = _load_counts()
                for mtype, name in models:
                    bucket = data.setdefault(mtype, {})
                    rec = bucket.get(name)
                    # 値が旧形式(int)や想定外の場合は新形式レコードを作り直す。
                    if not isinstance(rec, dict):
                        rec = {"count": 0, "last_used": None}
                    rec["count"] = rec.get("count", 0) + 1
                    rec["last_used"] = now
                    bucket[name] = rec
                _save_counts(data)
        else:
            data = _load_counts()  # 表示用に読むだけ(加算しない)

        # ノード上に現在の集計を表示(閲覧用。全カウンタで表示してよい)
        if data:
            t = DISPLAY_TEXT
            header = (t["col_count"], t["col_updated"], t["col_elapsed"], t["col_model"])
            right_align = (True, False, True, False)  # 使用回数・経過を右揃え(他は左揃え)
            lines = []
            for mtype in sorted(data):
                lines.append(f"[{mtype}]")
                entries = data[mtype]

                # 最終使用日時(last_used)の降順で並べる。
                #   - last_used は ISO 8601 文字列なので文字列比較で時系列順になる。
                #   - 同一日時はモデル名の昇順(二段ソートで安定させる)。
                #   - last_used が None / 旧int形式(dictでない)のレコードは降順ソートに
                #     巻き込まず末尾へまとめる(末尾内はモデル名昇順)。
                def _last_used(n):
                    r = entries[n]
                    return r.get("last_used") if isinstance(r, dict) else None

                dated = sorted(n for n in entries if _last_used(n))   # モデル名昇順
                dated.sort(key=_last_used, reverse=True)              # last_used 降順(安定)
                undated = sorted(n for n in entries if not _last_used(n))

                # 各行を (使用回数, 最終使用日時, 経過, モデル名) の4セルに整える。
                rows = []
                for name in dated + undated:
                    rec = entries[name]
                    if isinstance(rec, dict):
                        count = rec.get("count", 0)
                        lu = rec.get("last_used")
                        if lu:
                            updated, elapsed = _format_last_used_parts(lu)
                        else:                          # last_used 欠落のフォールバック
                            updated, elapsed = t["empty"], ""
                    else:                              # 旧int形式のフォールバック
                        count, updated, elapsed = rec, t["empty"], ""
                    rows.append((str(count), updated, elapsed, name))

                # 列幅をヘッダと全行の最大表示幅で決め、全角を考慮して揃える。
                widths = [
                    max(_disp_width(header[i]), *(_disp_width(r[i]) for r in rows))
                    if rows else _disp_width(header[i])
                    for i in range(4)
                ]

                def _row(cells):
                    parts = [_pad(cells[i], widths[i], right_align[i]) for i in range(4)]
                    return ("  " + "  ".join(parts)).rstrip()

                lines.append(_row(header))
                lines.extend(_row(r) for r in rows)
            text = "\n".join(lines)
        else:
            text = DISPLAY_TEXT["no_loaders"]

        return io.NodeOutput(ui=ui.PreviewText(text))


# フロントエンドに JS 拡張を配信する。
#   execute() が返す PreviewText(= "executed" イベントの message.text)を、
#   js/model_usage_counter.js がノード上の読み取り専用テキスト欄に描画する。
#   コア側の text 表示挙動はフロントのバージョンに依存して不確実なため、
#   自前のウィジェットで確実に表示させる。
WEB_DIRECTORY = "./js"


class ModelUsageCounterExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [ModelUsageCounter]


async def comfy_entrypoint() -> ModelUsageCounterExtension:
    return ModelUsageCounterExtension()