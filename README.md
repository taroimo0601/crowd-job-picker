# Crowd Job Picker（5大クラウドソーシング横断・特定条件ピックアップサイト）

完全無料（GitHub Actions + GitHub Pages）で定期自動収集・公開できる、自分専用のクラウドソーシング案件ピックアップサイトです。
サーバー代・データベース代・外部API課金は一切かからず（完全0円）、PC・スマホの両方から快適に案件をチェックできます。

---

## 主な機能

1. 5大クラウドソーシングサービス対応
   - クラウドワークス（CrowdWorks）
   - ランサーズ（Lancers）
   - ココナラ（coconala 公開依頼）
   - シュフティ（Shufti）
   - ママワークス（Mamaworks）

2. 特定条件による多段階フィルタリング＆スコアリング
   - サイト別フィルタ: 5サイトを個別にON/OFF可能
   - カテゴリ・職種フィルタ: システム開発・AI / Web制作・デザイン / 動画編集・制作 / ライティング・記事作成 / 事務・データ入力
   - キーワード検索（AND / OR 切替対応）
   - 除外キーワード（地雷案件ブロック）: 「スクール勧誘」「モニター募集」「1本100円」「LINE登録必須」などのNGワードを含む案件を自動ブロック
   - 報酬形態・最低単価フィルタ: 固定報酬○円以上、時給○円以上、「予算相談・未定を含めるか」の切り替え
   - 穴場絞り込み: 応募数上限（応募3件以下、5件以下など）で競争率の低い案件だけを抽出
   - 並び替え: 条件適合度スコア順 / 報酬額が高い順 / 応募数が少ない順（穴場順） / 締切が近い順 / 新着順

3. マイ条件プリセット保存＆リアルタイム横断検索ランチャー
   - よく使う絞り込み条件に名前を付けてワンクリックで保存・切り替え可能
   - 「現在の条件で実サイトを直接開く」ランチャーにより、入力中のキーワードを反映した状態で5サイトの検索結果ページを直接開くことも可能
   - 案件ごとの「お気に入り（★）」「応募済み・検討中（✓）」「見送り（非表示）」管理機能

---

## ローカルですぐに画面を確認する方法

ターミナルで以下のコマンドを実行し、ブラウザで `http://localhost:8080` を開くとすぐに動作確認ができます。

```bash
cd /Users/mizunotarou/Desktop/agy/crowd-job-picker
python3 -m http.server 8080 --directory docs
```

---

## 完全無料で運用開始する手順（GitHub Actions + GitHub Pages）

### ステップ1: GitHubリポジトリの作成とプッシュ
このフォルダ（`crowd-job-picker`）をGitHubの新しいリポジトリ（PublicリポジトリにするとGitHub Actionsの定期実行もGitHub Pagesも完全無料になります）にプッシュします。

```bash
cd /Users/mizunotarou/Desktop/agy/crowd-job-picker
git init
git add .
git commit -m "Initial commit: Crowd Job Picker"
git branch -M main
git remote add origin https://github.com/taroimo0601/crowd-job-picker.git
git push -u origin main
```

### ステップ2: GitHub Pagesの有効化
1. GitHubリポジトリの `Settings` > 左メニューの `Pages` を開きます。
2. Build and deployment の Source で `Deploy from a branch` を選択します。
3. Branch で `main`、フォルダで `/docs` を選択して `Save` を押します。
4. 1〜2分ほど待つと、`https://taroimo0601.github.io/crowd-job-picker/` でサイトが公開されます。

### ステップ3: 自動収集の確認・パスワード保護（任意）
1. リポジトリ上部の `Actions` タブを開き、`Update Crowdsourcing Jobs` を選択して `Run workflow` を押すと、今すぐ最新案件の収集がテスト実行されます（以降は毎日3時間おきに自動更新されます）。
2. もし自分以外の第三者に画面を見られたくない場合は、リポジトリの `Settings` > `Secrets and variables` > `Actions` にて、`New repository secret` から名前 `SITE_PASSWORD` に好きなパスワードを登録すると、自動的にパスワードロック画面が有効になります（未設定の場合はパスワードなしで即座に開けます）。
3. 収集対象のキーワードや初期プリセットをカスタマイズしたい場合は、`config/conditions.json` を編集するか、サイト右上の「⚙ 収集設定JSON」ボタンからJSONを出力して貼り付けてください。
