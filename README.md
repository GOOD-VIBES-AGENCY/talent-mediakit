# Talent Media Kit

週次の GitHub Actions は TikTok と YouTube の件数だけを更新します。Instagram の件数と投稿サムネイルは、GitHub のランナーでは取れないため、Cursor の VM から更新して PR にします。

cookie やログインは使いません。桃佳の Instagram 件数は `https://www.instagram.com/momoo_ka_` から取り、表示アカウントは変えません。

## Instagram だけ更新する

```bash
python3 scripts/refresh_followers.py --write --only instagram
python3 scripts/refresh_mediakit.py
```

件数の未取得があると最初のコマンドは終了コード 1 になります。その欄は前回の値のままです。画像は、取得できたものだけが置き換わります。酒巻茉侑の4枚目と乙の3枚目は、画像が無くても既存ファイルを残して失敗にしません。

## TikTok と YouTube も含めて更新する

```bash
python3 scripts/refresh_followers.py --write
python3 scripts/refresh_mediakit.py
```

Actions と同じく Instagram を触らない場合は `--skip-instagram` を付けます。
