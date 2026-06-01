// Model Usage Counter のノード上表示。
//   バックエンドは execute() で io.NodeOutput(ui=ui.PreviewText(text)) を返し、
//   生成完了時に "executed" イベントで message.text = [集計テキスト] を送ってくる。
//   ここではそれを受け取り、ノード上の読み取り専用の複数行テキスト欄に描画する。
//   (コア側の text 表示はフロントのバージョン依存で不確実なため、自前で描画する。)

import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

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

        // 生成完了ごとに呼ばれる。message.text に集計テキストが入っている。
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            const text = Array.isArray(message?.text)
                ? message.text.join("")
                : (message?.text ?? "");

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
