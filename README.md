# arxiv_summarize_bot
arXivからランダムに論文を抽出し、サマリしてSlackにpostするbotです。ChatGPTのgpt-3.5-turbo APIを使って下記のプロンプトに則って論文をサマリします。
Codeは下記の参考文献に則って作成しています。

# Prompt概要
1. タイトルの日本語訳
2. 背景課題
3. 要点3つ
4. 今後の展望
5. 想定され得る批判

## 今後の予定
1. lambdaでクラウドサーバ上で定期的に実行できるように
2. arXivはAPI経由で取得可能だが、他の論文誌もスクレイプして投稿できるように
3. 論文以外にも有益なニュースサイト等も情報ソースとできるように


## Special thanks to...
https://zenn.dev/ozushi/articles/ebe3f47bf50a86

https://zenn.dev/kou_pg_0131/articles/slack-api-post-message

https://qiita.com/KMD/items/bd59f2db778dd4bf6ed2

https://qiita.com/GleamingCake/items/e8c53fb0c1508ba1449e

https://github.com/zushi0516/arxiv_paper2slack
