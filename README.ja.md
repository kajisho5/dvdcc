<p><img src="docs/images/logo/lockup-dark.svg" alt="dvdcc" height="56"></p>

# dvdcc

**DVD** の MPEG-2 映像に、**ライン 21 のクローズドキャプション**（CEA-608、CC1）を入れます。再エンコードはせず、Python だけで動き、依存ライブラリはありません。

* **Scenarist（.scc）ファイルから**：キャプション制作ツールが書くバイト列を、タイムコードのフレームからそのまま使います。
* **字幕ファイルから**（SubRip・WebVTT・ASS / SSA・テキストスクリプト。UTF-8・UTF-16・Shift_JIS）：1 つずつポップオン方式のキャプションにします。
  * 表示時刻より前に裏のメモリへ読み込み、開始時刻に表示して、終了時刻に消します。
  * 32 桁・4 行に収まるよう折り返します。
  * 読み込みが間に合わないほど長いものは、遅れて表示し、そのことを知らせます。
* **映像への書き込み**：DVD の GOP ユーザーデータ（`00 00 01 B2 'C' 'C' 01 F8`）として、1 フレームに 1 組ずつ入れます。DVD プレーヤーがライン 21 に送るのは、このデータです。

## なぜ作ったか

DVD のキャプションを読み出すツールはありますが、入れるツールはほとんどありません。ffmpeg は .scc を埋め込めません。CEA-608 を書けるオープンソースのライブラリも、H.264 や HEVC（A/53 SEI）向けで、DVD の MPEG-2 のユーザーデータには対応していません。

## インストール

```sh
pip install dvdcc
```

リリースはバージョン番号で決まります。`pyproject.toml`（と `dvdcc/__init__.py`）のバージョンがまだタグの無い番号で `main` に入ると、`.github/workflows/release.yml` がテスト・ビルド・タグ付きの GitHub リリース・PyPI 公開（trusted publishing、環境 `pypi`）まで行います。バージョンを上げた PR をマージするだけで済みます。

## 使い方

```sh
dvdcc video.m2v captions.scc              # 映像ファイルをそのまま書き換え
dvdcc video.m2v subs.srt -o captioned.m2v --offset 01;00;00;00
```

```python
from dvdcc import captions

schedule, notes = captions.load("subs.srt")      # .scc も可
frames = captions.inject_file("video.m2v", schedule)
```

そのあとは通常どおり多重化してオーサリングします。オーサリングツールで、タイトルセットにライン 21 のキャプションがあると指定してください（dvdauthor なら `<video ... caption="field1"/>`）。プレーヤーはこの指定を見てキャプションを探します。

**制限**

* NTSC のみです（ライン 21 は 525 ラインの映像のものです）。
* 29.97 フレーム／秒のみです。ソフト 3:2 プルダウンのフィルム素材は、フィールドの数え方が違うため対応していません。
* フィールド 1（CC1）のみです。

## テスト

```sh
python -m unittest discover -s tests -t .
```

テストで確かめている内容は次のとおりです。

* キャプションのバイト列：パリティ、行・位置の指定コード、文字セット
* ポップオンのタイミングと Scenarist の読み込み
* ユーザーデータの並び
* ffmpeg がある場合：テスト映像に入れたキャプションを、**ffmpeg のキャプションデコーダ**（lavfi の `subcc`）が正しい時刻の文字として読み戻すこと
* dvdauthor もある場合：オーサリングしたディスクの VOB からキャプションが読め、IFO にライン 21 の印が付いていること

dvdcc は、DVD・Blu-ray オーサリングアプリ [oncemore](https://github.com/kajisho5/oncemore) の一部として作られました。

## 支援する

dvdcc は無料で、これからも無料です。役に立ったら [GitHub Sponsors](https://github.com/sponsors/kajisho5)（このリポジトリ上部の **Sponsor** ボタン）から開発を支援できます。不具合の報告も同じくらい助かります：[Issues](https://github.com/kajisho5/dvdcc/issues)。

ロゴ・色・文章の決まりは [docs/DESIGN.md](docs/DESIGN.md)（英語）にあります。

## ライセンス

Apache License 2.0（[LICENSE](LICENSE) と [NOTICE](NOTICE) を参照）。
