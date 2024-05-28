import os
#import yaml
import streamlit as st
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import arxiv
import openai
import random
from notion_client import Client

# Load API keys from config.yaml
#with open("config.yaml", "r") as f:
#    config = yaml.safe_load(f)

# Set up APIs
#openai.api_key = config["openai"]["api_key"]  # bot_summarize
#SLACK_API_TOKEN = config["slack"]["api_key"]  # slack_api_key
#NOTION_API_KEY = config["notion"]["api_key"] 
#NOTION_DATABASE_URL = config["notion"]["database_url"] 
openai.api_key = st.secrets.gptApiKey.key
SLACK_API_TOKEN = st.secrets.SlackApiKey.key
NOTION_API_KEY = st.secrets.NotionApiKey.key
NOTION_DATABASE_URL = st.secrets.NotionDatabaseUrl.key
notion_client = Client(auth=NOTION_API_KEY)

# Slackに投稿するチャンネル名を指定する
SLACK_CHANNEL = "#news-bot1"

default_prompt = """まず、与えられた論文の背景となっていた課題について述べてください。
次に、要点を3点、まとめて下さい。
更に、今後の展望をまとめてください。
最後に、与えられた論文について想定され得る批判を述べてください。
これらについては、以下のフォーマットで日本語で出力してください。
```
・タイトルの日本語訳
・背景課題
・要点1
・要点2
・要点3
・今後の展望
・想定される批判
    ```    
    """

def get_summary(prompt, result):
    text = f"title: {result.title}\nbody: {result.summary}"
    response = openai.ChatCompletion.create(
        model="gpt-4o-2024-05-13",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.25,
    )
    summary = response["choices"][0]["message"]["content"]
    title_en = result.title
    title, *body = summary.split("\n")
    body = "\n".join(body)
    date_str = result.published.strftime("%Y-%m-%d %H:%M:%S")
    message = f"発行日: {date_str}\n{result.entry_id}\n{title_en}\n{title}\n{body}\n"

    return message

def add_summary_to_notion(summary):
    notion_client.pages.create(**{
        "parent": { 
            'database_id': NOTION_DATABASE_URL
        },
        "properties": {
            "Name": {
            "title": [
            {
                "text": {
                "content": summary["title"]
                }
            }
            ],
        },

        "Tags":{
            "multi_select":[
                {
                    "name": "arXiv"
                    }
            ]
        },

        "Published":{
                "date":{
                    "start": summary["date"]
                }
        },

        "URL": {
                "url": summary["url"]
            }

        },

        "children": [
        {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{ 
                "type": "text", 
                "text": { 
                    "content": summary["summary"]
                } 
            }]
        }
        }
    ]
    })

def main():
    # Slack APIクライアントを初期化する
    client = WebClient(token=SLACK_API_TOKEN)

    st.title("Paper Summary by ChatGPT")
    paper_title = st.text_input("arXivの論文のタイトルを入力してください:")

    custom_prompt = st.text_area("プロンプトをカスタマイズしてください:", value=default_prompt, height=200)

    if st.button("論文を検索して要約"):
        query = f'ti:"{paper_title}"'

        # arxiv APIで最新の論文情報を取得する
        search = arxiv.Search(
            query=query,
            max_results=1,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        # searchの結果をリストに格納
        result_list = []
        for result in search.results():
            result_list.append(result)
            
        # ランダムにnum_papersの数だけ選ぶ
        #num_papers = 1
        #results = random.sample(result_list, k=num_papers)

        summary = {
        "title": result.title,
        "summary": get_summary(custom_prompt, result),
        "url": result.entry_id,
        "date": result.published.strftime("%Y-%m-%d"),
        }

        # 論文情報をSlackに投稿し、Streamlit上にも表示する
        result = result_list[0]
        try:
            # プロンプトをカスタマイズ
            system = custom_prompt

            # Slackに投稿するメッセージを組み立てる
            message = "論文のサマリです。\n" + get_summary(custom_prompt, result)

            # Slackにメッセージを投稿する
            response = client.chat_postMessage(
                channel=SLACK_CHANNEL,
                text=message
            )
            st.success("メッセージが投稿されました。")
            st.write("### サマリ:")
            st.write(message)
            print(f"Message posted: {response['ts']}")

        except SlackApiError as e:
            st.error("メッセージの投稿中にエラーが発生しました。")
            print(f"Error posting message: {e}")

        # Add the summary to the Notion database
        try:
            add_summary_to_notion(summary)
            st.success("サマリがNotionデータベースに追加されました。")

        except Exception as e:
            st.error("サマリのNotionデータベースへの追加中にエラーが発生しました。")
            print(f"Error adding summary to Notion: {e}")

if __name__ == '__main__':
    main()
