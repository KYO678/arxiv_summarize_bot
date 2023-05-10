import os
import yaml
import streamlit as st
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import arxiv
import openai
import random

# Load API keys from config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Set up APIs
openai.api_key = config["openai"]["api_key"]  # bot_summarize
SLACK_API_TOKEN = config["slack"]["api_key"]  # slack_api_key

# Slackに投稿するチャンネル名を指定する
SLACK_CHANNEL = "#news-bot1"


def get_summary(result):
    system = """まず、与えられた論文の背景となっていた課題、要点3点、今後の展望をまとめ、以下のフォーマットで日本語で出力してください。```
    タイトルの日本語訳
    ・背景課題
    ・要点1
    ・要点2
    ・要点3
    ・今後の展望
    ```
    また、与えられた論文について想定され得る批判を述べてください。
    """

    text = f"title: {result.title}\nbody: {result.summary}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system},
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


def main():
    # Slack APIクライアントを初期化する
    client = WebClient(token=SLACK_API_TOKEN)

    st.title("Paper Summary by ChatGPT")
    paper_title = st.text_input("arXivの論文のタイトルを入力してください:")

    default_prompt = """まず、与えられた論文の背景となっていた課題、要点3点、今後の展望をまとめ、以下のフォーマットで日本語で出力してください。```
    タイトルの日本語訳
    ・背景課題
    ・要点1
    ・要点2
    ・要点3
    ・今後の展望
    ```
    また、与えられた論文について想定され得る批判を述べてください。
    """
    custom_prompt = st.text_area("プロンプトをカスタマイズしてください:", value=default_prompt, height=200)

    if st.button("検索してSlackに通知"):
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
        num_papers = 1
        results = random.sample(result_list, k=num_papers)

        # 論文情報をSlackに投稿し、Streamlit上にも表示する
        for i, result in enumerate(results):
            try:
                # プロンプトをカスタマイズ
                system = custom_prompt

                # Slackに投稿するメッセージを組み立てる
                message = "論文のサマリです。\n" + get_summary(result)

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

if __name__ == '__main__':
    main()