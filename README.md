# localcut

**Footage stays home. Words go to the cloud.**（映像は手元、言葉は空へ）

旅先で撮った動画を、その場でローカルLLMに編集させるハイブリッド編集パイプラインです。

```
 [手元 / 夜にバッチ]                                  [クラウド / 朝に対話]
 素材 (GB) ─ シーン検出 ─ キーフレーム ─ 顔ぼかし          Claude Code / Copilot
                 └─ ローカルVLMで1ショット1行のテキスト ─▶ egress gate ─▶ 編集ブリーフ (KB)
                                                                     │
 縦動画 1080x1920 ◀─ ローカルで書き出し・顔ぼかし・テロップ ◀── 編集プラン (JSON テキスト)
```

- 生の映像（数十GB、人の顔、圏外で撮った素材）は手元から出しません。
- ローカルのVLMが、映像を1ショット1行の「編集ブリーフ（テキスト）」に変えます。
- クラウドLLMは、そのテキストだけを読んで構成・タイトル・テロップを決めます。
- 書き出し（顔ぼかし、テロップの焼き込み）はローカルで行います。
- MCPツールの戻り値はすべて **egress gate** を通ります。マスク処理と容量上限をかけ、送ったテキストを全文記録します。

## 必要なもの

| もの | 用途 | 確認したもの（Windows on ARM64） |
|---|---|---|
| Python 3.11 以上 | パイプラインと MCP サーバー | 3.11.9 ARM64 |
| ffmpeg / ffprobe（libass・libx264 入り） | シーン検出、キーフレーム、書き出し | BtbN FFmpeg-Builds `winarm64-gpl` n8.1 |
| LM Studio | ローカル VLM（OpenAI 互換 API） | 0.4.29 ARM64 + `google/gemma-4-e4b` |
| YuNet ONNX（任意） | 顔検出 | `face_detection_yunet_2023mar.onnx`（opencv_zoo） |

```powershell
python -m venv .venv
# Windows on ARM64: cryptography (mcp の依存) はビルド済み wheel を使う
.venv\Scripts\pip install --prefer-binary --only-binary cryptography -r requirements.txt onnxruntime
.venv\Scripts\python -m localcut doctor
```

素材・作業ファイル・ツールは、既定でリポジトリの外（隣の `localcut-private\{footage,work,runs,tools}`）に置きます。
場所は `LOCALCUT_FOOTAGE_DIR` / `LOCALCUT_WORK_DIR` / `LOCALCUT_RUNS_DIR` / `LOCALCUT_TOOLS_DIR` で変えられます。
LM Studio の設定は公式キットと同じ `SPARK_LMSTUDIO_URL` / `SPARK_VISION_MODEL` を読みます。

## 使い方

```powershell
# 夜: 手元だけで解析（ネットワーク不要）
.venv\Scripts\python -m localcut analyze      # シーン検出・キーフレーム・顔検出
.venv\Scripts\python -m localcut caption      # ローカル VLM で 1 ショット 1 行
.venv\Scripts\python -m localcut brief        # クラウドに渡る前のブリーフを確認
```

朝は Claude Code をこのフォルダで開き、`/vlog-edit 40秒くらい、のんびりした雰囲気で` と頼みます。
Claude は MCP ツール（`footage_status` → `get_edit_brief` → `submit_edit_plan` → `render_preview` → `review_render` → `egress_report`）だけで編集します。
GitHub Copilot（CLI / VS Code）では `.github/prompts/vlog-edit.prompt.md` を使います。サーバーの起動コマンドは同じです。

## egress gate がやること・やらないこと

- 許可した項目だけでブリーフを組み立てます。パス、ファイル名、撮影日時、GPS、顔の座標は含めません。
- 電話番号・メール・郵便番号・住所・ナンバー・URL・パス・座標・時刻をマスクします。`LOCALCUT_GATE_LLM=1` で、ローカルLLMによる固有名詞チェックを追加できます。
- 容量の上限を超えたら、何も送らずに止めます（fail closed）。
- 送ったテキストは `runs/egress/` に全文で、送信の記録は `runs/egress.jsonl` に残します。
- **サンドボックスではありません。** このサーバーが返すものを制御するだけです。クライアント側でファイルを読ませない設定（`.claude/settings.json` の deny）と組み合わせて使ってください。

## 謝辞

[Surface-Laptop-Ultra-RTX-Spark-Vibe-Coding-kit](https://github.com/dahatake/Surface-Laptop-Ultra-RTX-Spark-Vibe-Coding-kit)（MIT）の考え方「判断と統合はクラウド、生データと反復処理はローカル」と、コードの一部を元にしています。詳細は [NOTICE](./NOTICE) を参照してください。

## License

MIT
