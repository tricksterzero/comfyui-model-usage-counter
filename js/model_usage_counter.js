// Model Usage Counter のノード上表示。
//   バックエンドは execute() で集計テキストを言語別に整形し、生成完了時の "executed"
//   イベントで message.text(英語・既定) / message.text_en / message.text_ja を送ってくる。
//   ここでは ComfyUI のロケールに応じた言語のテキストを受け取り、ノード上の
//   読み取り専用の複数行テキスト欄に描画する。
//   (コア側の text 表示はフロントのバージョン依存で不確実なため、自前で描画する。)

import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// ComfyUI のロケール(Comfy.Locale)から表示言語(ja / en)を決める。
//   - ロケール変更時 ComfyUI はリロードを促すため、描画時の読み取りで設定と一致する。
//   - 設定 API → localStorage → ブラウザ言語 の順にフォールバックする。
//   - ja で始まるロケールのみ日本語。それ以外は英語(グローバル既定)。
function pickLang() {
    let loc = "";
    try {
        loc = app.ui?.settings?.getSettingValue?.("Comfy.Locale") || "";
    } catch (e) {
        // 設定 API 未対応バージョンはフォールバックへ。
    }
    if (!loc) {
        const raw =
            localStorage["Comfy.Settings.Comfy.Locale"] ||
            localStorage["AGL.Locale"] ||
            localStorage["Comfy.Settings.AGL.Locale"];
        if (raw) {
            try {
                loc = JSON.parse(raw);
            } catch (e) {
                loc = raw;
            }
        }
    }
    if (!loc) {
        loc = navigator.language || "en";
    }
    return String(loc).toLowerCase().startsWith("ja") ? "ja" : "en";
}

app.registerExtension({
    name: "MUC.ModelUsageCounter",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== "MUC_ModelUsageCounter") {
            return;
        }

        // 表示用ウィジェットを取得する(無ければ作成)。
        function ensureDisplayWidget(node) {
            let widget = node.widgets?.find((w) => w.name === "muc_display");
            if (widget) {
                return widget;
            }
            widget = ComfyWidgets["STRING"](
                node,
                "muc_display",
                ["STRING", { multiline: true }],
                app
            ).widget;
            // 閲覧専用。編集不可・見た目を少し控えめにする。
            widget.inputEl.readOnly = true;
            widget.inputEl.style.opacity = 0.75;
            // 表示専用なのでワークフローには保存しない。
            widget.serializeValue = async () => undefined;
            return widget;
        }

        // 生成完了ごとに呼ばれる。message に言語別の集計テキスト(text / text_en / text_ja)が入る。
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            // ロケールに応じた言語キー(text_ja / text_en)を選び、無ければ text にフォールバック。
            const lang = pickLang();
            const picked = message?.["text_" + lang] ?? message?.text;
            const text = Array.isArray(picked)
                ? picked.join("")
                : (picked ?? "");

            const widget = ensureDisplayWidget(this);
            widget.value = text;

            // テキスト量に合わせてノードを広げ、再描画する。
            requestAnimationFrame(() => {
                const size = this.computeSize();
                this.size[0] = Math.max(this.size[0], size[0]);
                this.size[1] = Math.max(this.size[1], size[1]);
                this.onResize?.(this.size);
                app.graph?.setDirtyCanvas(true, false);
            });
        };
    },
});
