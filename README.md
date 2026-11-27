# localcut

**Footage stays home. Words go to the cloud.**（映像は手元、言葉は空へ）

旅先で撮った動画を、その場でローカルLLMに編集させるためのハイブリッド編集パイプラインです。

- 生の映像（数十GB、人の顔、圏外で撮った素材）は手元から出しません。
- ローカルのVLMと音声認識が、映像を数KBの「編集ブリーフ（テキスト）」に変えます。
- クラウドLLMに渡すのはそのテキストだけです。構成・タイトル・テロップをテキストで返してもらいます。
- 書き出しはローカルで行います。
- クラウドに何バイト送ったかは、すべて記録して見せます（egress gate）。

ローカルのツールは MCP サーバーとして公開するので、Claude Code からも GitHub Copilot（CLI / VS Code）からも呼べます。

## 状態

開発中です（v0.1）。Windows on ARM64（Snapdragon X）で開発しています。

## 必要なもの

| もの | 用途 |
|---|---|
| Python 3.11 以上 | パイプラインと MCP サーバー |
| ffmpeg / ffprobe | シーン検出、キーフレーム、書き出し |
| LM Studio | ローカルの VLM / LLM（OpenAI 互換 API） |
| whisper.cpp | ローカルの音声認識 |

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m localcut doctor
```

素材と作業ファイルは、既定でリポジトリの外（隣の `localcut-private\`）に置きます。場所は `LOCALCUT_FOOTAGE_DIR` / `LOCALCUT_WORK_DIR` で変えられます。

## 謝辞

[Surface-Laptop-Ultra-RTX-Spark-Vibe-Coding-kit](https://github.com/dahatake/Surface-Laptop-Ultra-RTX-Spark-Vibe-Coding-kit)（MIT）の考え方「判断と統合はクラウド、生データと反復処理はローカル」とコードの一部を元にしています。詳細は [NOTICE](./NOTICE) を参照してください。

## License

MIT
