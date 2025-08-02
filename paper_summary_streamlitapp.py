import streamlit as st
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import openai
from notion_client import Client
import re
import time
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pickle
import os

# ページ設定
st.set_page_config(
    page_title="📚 Paper Summary by LLM",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS - ダークモード & 大人っぽい配色
st.markdown("""
<style>
    /* 全体のベース設定 */
    .stApp {
        background-color: #262236;
        color: #fefef3;
    }
    
    /* サイドバー */
    .css-1d391kg {
        background-color: #3d4f7e;
    }
    
    /* メインヘッダー */
    .main-header {
        text-align: center;
        padding: 3rem 0;
        background: linear-gradient(135deg, #3d4f7e 0%, #262236 50%, #e18546 100%);
        color: #fefef3;
        margin: -1rem -1rem 2rem -1rem;
        border-radius: 0 0 20px 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        position: relative;
        overflow: hidden;
    }
    
    .main-header::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: radial-gradient(circle at 30% 40%, rgba(225, 133, 70, 0.1) 0%, transparent 50%);
        pointer-events: none;
    }
    
    .main-header h1 {
        font-size: 2.8rem;
        margin-bottom: 0.5rem;
        font-weight: 700;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    }
    
    .main-header p {
        font-size: 1.3rem;
        opacity: 0.9;
        font-weight: 300;
    }
    
    /* 検索方法コンテナ */
    .search-method-container {
        background: linear-gradient(135deg, #3d4f7e 0%, #495a8a 100%);
        padding: 1.5rem;
        border-radius: 15px;
        border: 1px solid #4a5c91;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    
    /* 論文情報ボックス */
    .paper-info-box {
        background: linear-gradient(135deg, #3d4f7e 0%, #495a8a 100%);
        border: 2px solid #e18546;
        border-radius: 15px;
        padding: 2rem;
        margin: 1.5rem 0;
        box-shadow: 0 8px 32px rgba(225, 133, 70, 0.1);
        position: relative;
        overflow: hidden;
    }
    
    .paper-info-box::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 4px;
        background: linear-gradient(90deg, #e18546 0%, #f4a261 100%);
    }
    
    /* 要約ボックス */
    .summary-box {
        background: linear-gradient(135deg, #2a1f3d 0%, #3d4f7e 100%);
        border-left: 6px solid #e18546;
        border-radius: 0 15px 15px 0;
        padding: 2rem;
        margin: 1.5rem 0;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        position: relative;
    }
    
    .summary-box::after {
        content: "";
        position: absolute;
        right: 20px;
        top: 20px;
        width: 40px;
        height: 40px;
        background: radial-gradient(circle, #e18546 0%, transparent 70%);
        border-radius: 50%;
        opacity: 0.3;
    }
    
    /* メッセージボックス */
    .success-message {
        background: linear-gradient(135deg, #2d5016 0%, #52b788 100%);
        color: #fefef3;
        border: 1px solid #52b788;
        border-radius: 12px;
        padding: 1.2rem;
        margin: 1rem 0;
        box-shadow: 0 4px 16px rgba(82, 183, 136, 0.2);
    }
    
    .error-message {
        background: linear-gradient(135deg, #8b2635 0%, #e63946 100%);
        color: #fefef3;
        border: 1px solid #e63946;
        border-radius: 12px;
        padding: 1.2rem;
        margin: 1rem 0;
        box-shadow: 0 4px 16px rgba(230, 57, 70, 0.2);
    }
    
    .warning-message {
        background: linear-gradient(135deg, #b5651d 0%, #e18546 100%);
        color: #fefef3;
        border: 1px solid #e18546;
        border-radius: 12px;
        padding: 1.2rem;
        margin: 1rem 0;
        box-shadow: 0 4px 16px rgba(225, 133, 70, 0.2);
    }
    
    /* フッター */
    .footer-tips {
        background: linear-gradient(135deg, #2a1f3d 0%, #3d4f7e 100%);
        border-radius: 15px;
        padding: 2rem;
        margin-top: 2rem;
        border: 1px solid #4a5c91;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }
    
    /* ボタンスタイル */
    .stButton > button {
        width: 100%;
        border-radius: 12px;
        font-weight: 600;
        transition: all 0.3s ease;
        background: linear-gradient(135deg, #e18546 0%, #f4a261 100%);
        border: none;
        color: #262236;
        font-size: 1rem;
        padding: 0.6rem 1.2rem;
        box-shadow: 0 4px 16px rgba(225, 133, 70, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(225, 133, 70, 0.4);
        background: linear-gradient(135deg, #f4a261 0%, #e76f51 100%);
    }
    
    .stButton > button:active {
        transform: translateY(0px);
        box-shadow: 0 4px 16px rgba(225, 133, 70, 0.3);
    }
    
    /* プライマリボタン */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #3d4f7e 0%, #495a8a 100%);
        color: #fefef3;
        box-shadow: 0 4px 16px rgba(61, 79, 126, 0.3);
    }
    
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #495a8a 0%, #5a6ba3 100%);
        box-shadow: 0 8px 24px rgba(61, 79, 126, 0.4);
    }
    
    /* 入力フィールド */
    .stTextInput > div > div > input {
        background-color: #3d4f7e;
        color: #fefef3;
        border: 2px solid #4a5c91;
        border-radius: 10px;
        padding: 0.7rem;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #e18546;
        box-shadow: 0 0 10px rgba(225, 133, 70, 0.3);
    }
    
    /* セレクトボックス */
    .stSelectbox > div > div > select {
        background-color: #3d4f7e;
        color: #fefef3;
        border: 2px solid #4a5c91;
        border-radius: 10px;
    }
    
    /* テキストエリア */
    .stTextArea > div > div > textarea {
        background-color: #3d4f7e;
        color: #fefef3;
        border: 2px solid #4a5c91;
        border-radius: 10px;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #e18546;
        box-shadow: 0 0 10px rgba(225, 133, 70, 0.3);
    }
    
    /* ラジオボタン */
    .stRadio > div {
        background-color: rgba(61, 79, 126, 0.3);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #4a5c91;
    }
    
    /* エキスパンダー */
    .streamlit-expanderHeader {
        background-color: #3d4f7e;
        color: #fefef3;
        border-radius: 10px;
        border: 1px solid #4a5c91;
    }
    
    .streamlit-expanderContent {
        background-color: rgba(61, 79, 126, 0.2);
        border: 1px solid #4a5c91;
        border-top: none;
        border-radius: 0 0 10px 10px;
    }
    
    /* メトリクス */
    .metric-container {
        background: linear-gradient(135deg, #3d4f7e 0%, #495a8a 100%);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #4a5c91;
        margin: 0.5rem 0;
    }
    
    /* スピナー */
    .stSpinner {
        color: #e18546 !important;
    }
    
    /* マークダウンのコードブロック */
    .stMarkdown code {
        background-color: #2a1f3d;
        color: #e18546;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
        border: 1px solid #4a5c91;
    }
    
    /* プログレスバー */
    .stProgress > div > div > div {
        background-color: #e18546;
    }
    
    /* 情報ボックス */
    .stInfo {
        background-color: rgba(61, 79, 126, 0.3);
        border-left: 4px solid #e18546;
        color: #fefef3;
    }
    
    /* 列の区切り線 */
    .element-container {
        border-right: 1px solid rgba(254, 254, 243, 0.1);
    }
    
    /* カスタムアクセント */
    .accent-gradient {
        background: linear-gradient(45deg, #e18546, #3d4f7e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: bold;
    }
    
    /* ホバーエフェクト */
    .hover-glow:hover {
        box-shadow: 0 0 20px rgba(225, 133, 70, 0.3);
        transition: all 0.3s ease;
    }
    
    /* スクロールバー */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #262236;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #e18546;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #f4a261;
    }
</style>
""", unsafe_allow_html=True)

# 定数
SLACK_CHANNEL = "#news-bot1"
CACHE_DIR = "arxiv_cache"
ARXIV_API_BASE = "http://export.arxiv.org/api/query"

GPT_MODELS = {
    "GPT-4o": "gpt-4o-2024-08-06",
    "GPT-4.1 nano": "gpt-4.1-nano-2025-04-14", 
    "GPT-4.1": "gpt-4.1-2025-04-14",
    "o3": "o3-2025-04-16"
}

DEFAULT_PROMPT = """まず、与えられた論文の背景となっていた課題について述べてください。
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

def load_config():
    """Streamlit Secretsから設定を読み込み"""
    try:
        # Streamlit Secretsから読み込み
        config = {
            'api_keys': {
                'openai': st.secrets["gptApiKey"]["key"],
                'slack': st.secrets["SlackApiKey"]["key"],
                'notion': st.secrets["NotionApiKey"]["key"]
            },
            'settings': {
                'notion_database_url': st.secrets["NotionDatabaseUrl"]["key"],
                'slack_channel': SLACK_CHANNEL
            }
        }
        
        # 必要なキーの存在確認
        for key, value in config['api_keys'].items():
            if not value:
                st.error(f"❌ {key} APIキーが設定されていません。")
                st.stop()
        
        return config
        
    except Exception as e:
        st.error(f"""
        ❌ シークレット設定エラー: {e}
        
        GitHub Secretsまたは.streamlit/secrets.tomlに以下の形式で設定してください：
        
        ```toml
        [gptApiKey]
        key = "your-openai-api-key"
        
        [SlackApiKey]
        key = "your-slack-bot-token"
        
        [NotionApiKey]
        key = "your-notion-api-key"
        
        [NotionDatabaseUrl]
        key = "your-notion-database-id"
        ```
        """)
        st.stop()

# 改良されたarXiv検索クラス
class ImprovedArxivSearch:
    def __init__(self, cache_dir=CACHE_DIR):
        self.api_base = ARXIV_API_BASE
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def extract_arxiv_id_from_url(self, url):
        """arXiv URLからIDを抽出する"""
        try:
            patterns = [
                r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)',
                r'arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)\.pdf',
                r'^([0-9]{4}\.[0-9]{4,5}v?[0-9]*)$',
                r'arxiv\.org/abs/([a-z-]+/[0-9]{7})',  # 古い形式
                r'arxiv\.org/pdf/([a-z-]+/[0-9]{7})'   # 古い形式
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    arxiv_id = match.group(1)
                    # バージョン番号を削除
                    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
                    return arxiv_id
            
            return None
        except Exception:
            return None
    
    def get_cached_results(self, query, max_age_hours=6):
        """キャッシュから結果を取得"""
        cache_path = os.path.join(self.cache_dir, f"{hash(query)}.pkl")
        
        if os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if datetime.now() - mtime < timedelta(hours=max_age_hours):
                try:
                    with open(cache_path, 'rb') as f:
                        return pickle.load(f)
                except Exception:
                    os.remove(cache_path)
        
        return None
    
    def save_results(self, query, results):
        """結果をキャッシュに保存"""
        cache_path = os.path.join(self.cache_dir, f"{hash(query)}.pkl")
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(results, f)
        except Exception as e:
            st.warning(f"キャッシュ保存に失敗: {e}")
    
    def search_arxiv_api(self, query, max_results=5, retry_count=3):
        """直接arXiv APIで検索"""
        params = {
            'search_query': query,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        for attempt in range(retry_count):
            try:
                response = requests.get(self.api_base, params=params, timeout=30)
                response.raise_for_status()
                
                # XMLパース
                root = ET.fromstring(response.content)
                
                # 名前空間の設定
                namespaces = {
                    'atom': 'http://www.w3.org/2005/Atom',
                    'arxiv': 'http://arxiv.org/schemas/atom'
                }
                
                entries = root.findall('atom:entry', namespaces)
                if not entries:
                    return None
                
                # 最初のエントリを取得
                entry = entries[0]
                
                # メタデータの抽出
                paper_data = {
                    'id': entry.find('atom:id', namespaces).text.split('/')[-1],
                    'title': entry.find('atom:title', namespaces).text.strip(),
                    'summary': entry.find('atom:summary', namespaces).text.strip(),
                    'published': entry.find('atom:published', namespaces).text,
                    'updated': entry.find('atom:updated', namespaces).text,
                    'authors': [author.find('atom:name', namespaces).text 
                               for author in entry.findall('atom:author', namespaces)],
                    'categories': [cat.get('term') 
                                  for cat in entry.findall('atom:category', namespaces)]
                }
                
                # URL情報を追加
                paper_data['entry_id'] = f"http://arxiv.org/abs/{paper_data['id']}"
                paper_data['pdf_url'] = f"http://arxiv.org/pdf/{paper_data['id']}.pdf"
                
                # 日付情報をdatetimeオブジェクトに変換
                try:
                    paper_data['published_datetime'] = datetime.fromisoformat(paper_data['published'].replace('Z', '+00:00'))
                except:
                    paper_data['published_datetime'] = datetime.now()
                
                return paper_data
                
            except requests.RequestException as e:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                if attempt < retry_count - 1:
                    st.warning(f"⚠️ API接続エラー（{attempt + 1}/{retry_count}）。{wait_time:.1f}秒後にリトライします...")
                    time.sleep(wait_time)
                else:
                    st.error(f"❌ API接続に失敗しました: {e}")
                    
            except ET.ParseError as e:
                st.error(f"❌ XMLパースエラー: {e}")
                break
                
        return None
    
    def search_by_id(self, arxiv_id):
        """IDで論文を検索"""
        cache_key = f"id:{arxiv_id}"
        cached_result = self.get_cached_results(cache_key)
        if cached_result:
            st.info("🗄️ キャッシュから結果を取得しました")
            return cached_result
        
        # ID検索用のパラメータ
        params = {
            'id_list': arxiv_id,
            'max_results': 1
        }
        
        try:
            response = requests.get(self.api_base, params=params, timeout=30)
            response.raise_for_status()
            
            # XMLパース
            root = ET.fromstring(response.content)
            
            # 名前空間の設定
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            entry = root.find('atom:entry', namespaces)
            if entry is None:
                return None
            
            # メタデータの抽出
            paper_data = {
                'id': entry.find('atom:id', namespaces).text.split('/')[-1],
                'title': entry.find('atom:title', namespaces).text.strip(),
                'summary': entry.find('atom:summary', namespaces).text.strip(),
                'published': entry.find('atom:published', namespaces).text,
                'updated': entry.find('atom:updated', namespaces).text,
                'authors': [author.find('atom:name', namespaces).text 
                           for author in entry.findall('atom:author', namespaces)],
                'categories': [cat.get('term') 
                              for cat in entry.findall('atom:category', namespaces)]
            }
            
            # URL情報を追加
            paper_data['entry_id'] = f"http://arxiv.org/abs/{paper_data['id']}"
            paper_data['pdf_url'] = f"http://arxiv.org/pdf/{paper_data['id']}.pdf"
            
            # 日付情報をdatetimeオブジェクトに変換
            try:
                paper_data['published_datetime'] = datetime.fromisoformat(paper_data['published'].replace('Z', '+00:00'))
            except:
                paper_data['published_datetime'] = datetime.now()
            
            # キャッシュに保存
            self.save_results(cache_key, paper_data)
            
            return paper_data
            
        except Exception as e:
            st.error(f"❌ ID検索エラー: {e}")
            return None
    
    def search_by_title(self, title):
        """タイトルで論文を検索"""
        cache_key = f"title:{title}"
        cached_result = self.get_cached_results(cache_key)
        if cached_result:
            st.info("🗄️ キャッシュから結果を取得しました")
            return cached_result
        
        # まず完全一致検索を試行
        query = f'ti:"{title}"'
        result = self.search_arxiv_api(query, max_results=3)
        
        if result:
            self.save_results(cache_key, result)
            return result
        
        # 完全一致で見つからない場合、部分一致検索
        st.info("🔍 完全一致で見つからなかったため、部分一致検索を実行中...")
        result = self.search_arxiv_api(f"all:{title}", max_results=5)
        
        if result:
            self.save_results(cache_key, result)
            return result
        
        return None

# キャッシュクラス
class ArxivCache:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def get_cached_results(self, query, max_age_hours=24):
        cache_path = os.path.join(self.cache_dir, f"{hash(query)}.pkl")
        
        if os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if datetime.now() - mtime < timedelta(hours=max_age_hours):
                try:
                    with open(cache_path, 'rb') as f:
                        return pickle.load(f)
                except Exception:
                    os.remove(cache_path)
        
        return None
    
    def save_results(self, query, results):
        cache_path = os.path.join(self.cache_dir, f"{hash(query)}.pkl")
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(results, f)
        except Exception as e:
            st.warning(f"キャッシュ保存に失敗: {e}")

# API設定とエラーハンドリング
@st.cache_resource
def initialize_apis():
    """API初期化（キャッシュ）"""
    config = load_config()
    
    try:
        # API キーの取得
        openai_key = config['api_keys']['openai']
        slack_token = config['api_keys']['slack']
        notion_key = config['api_keys']['notion']
        notion_db_url = config['settings']['notion_database_url']
        
        # OpenAI初期化
        openai.api_key = openai_key
        
        # Notion初期化
        notion_client = Client(auth=notion_key)
        
        # Slack初期化
        slack_client = WebClient(token=slack_token)
        
        # 改良されたarXiv検索クライアント
        arxiv_search = ImprovedArxivSearch()
        
        return {
            "openai_key": openai_key,
            "slack_client": slack_client,
            "notion_client": notion_client,
            "notion_db_url": notion_db_url,
            "arxiv_search": arxiv_search,
            "cache": ArxivCache(),
            "config": config
        }
    except Exception as e:
        st.error(f"⚠️ API初期化エラー: {e}")
        st.stop()

def search_paper_by_title(title, apis):
    """タイトルで論文を検索"""
    try:
        result = apis["arxiv_search"].search_by_title(title)
        return result
    except Exception as e:
        st.error(f"❌ 論文検索エラー: {e}")
        return None

def search_paper_by_id(arxiv_id, apis):
    """arXiv IDで論文を検索"""
    try:
        result = apis["arxiv_search"].search_by_id(arxiv_id)
        return result
    except Exception as e:
        st.error(f"❌ 論文取得エラー: {e}")
        return None

def get_summary(prompt, result, model, apis):
    """論文要約を生成（修正版）"""
    if not prompt.strip():
        st.error("❌ プロンプトが空です。")
        return None
        
    text = f"title: {result['title']}\nbody: {result['summary']}"
    
    try:
        # 古いAPI形式を先に試す
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.25,
        )
        summary = response["choices"][0]["message"]["content"]
        
    except Exception as e:
        # 新しいAPI形式でリトライ
        try:
            client = openai.OpenAI(api_key=apis["openai_key"])
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.25,
                max_tokens=2000,
            )
            summary = response.choices[0].message.content
        except Exception as e2:
            st.error(f"❌ OpenAI APIエラー: {e2}")
            return None
    
    if not summary:
        st.error("❌ 要約が生成されませんでした。")
        return None
    
    # サマリーのみを返す（メッセージフォーマットは後で追加）
    return summary

def add_summary_to_notion(summary_data, apis):
    """Notionに要約を追加（動作確認済みのシンプル版）"""
    try:
        # Database IDをそのまま使用
        notion_db_id = apis["notion_db_url"]
        
        # ページ作成データ
        result = apis["notion_client"].pages.create(
            parent={"database_id": notion_db_id},
            properties={
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": summary_data["title"]
                            }
                        }
                    ]
                },
                "Tags": {
                    "multi_select": [
                        {
                            "name": "arXiv"
                        }
                    ]
                },
                "Published": {
                    "date": {
                        "start": summary_data["date"]
                    }
                },
                "URL": {
                    "url": summary_data["url"]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": summary_data["summary"][:2000]  # Notion制限
                                }
                            }
                        ]
                    }
                }
            ]
        )
        
        return True, "Notionに保存されました"
        
    except Exception as e:
        return False, f"Notion API エラー: {str(e)}"

def post_to_slack(message, apis):
    """Slackにメッセージを投稿（動作確認済みのシンプル版）"""
    try:
        # チャンネル名を取得
        channel = apis["config"]["settings"].get("slack_channel", SLACK_CHANNEL)
        
        # Slack投稿
        response = apis["slack_client"].chat_postMessage(
            channel=channel,
            text=message
        )
        
        if response["ok"]:
            return True, "Slackに投稿されました"
        else:
            return False, f"Slack エラー: {response.get('error', 'Unknown')}"
            
    except SlackApiError as e:
        return False, f"Slack API エラー: {e.response['error']}"
    except Exception as e:
        return False, f"Slack投稿エラー: {str(e)}"

def display_paper_info(result):
    """論文情報を表示"""
    st.markdown('<div class="paper-info-box">', unsafe_allow_html=True)
    st.markdown("### 📄 論文情報")
    
    st.write(f"**タイトル:** {result['title']}")
    st.write(f"**発行日:** {result['published_datetime'].strftime('%Y-%m-%d')}")
    st.write(f"**URL:** {result['entry_id']}")
    
    try:
        if result['authors']:
            displayed_authors = result['authors'][:10]
            author_text = ", ".join(displayed_authors)
            if len(result['authors']) > 10:
                author_text += f" 他 {len(result['authors']) - 10} 名"
            st.write(f"**著者:** {author_text}")
    except Exception:
        st.write("**著者:** 情報取得できませんでした")
    
    if result.get('categories'):
        st.write(f"**カテゴリ:** {', '.join(result['categories'][:5])}")
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    # 初期化
    apis = initialize_apis()
    
    # ヘッダー
    st.markdown("""
    <div class="main-header">
        <h1>📚 Paper Summary by ChatGPT</h1>
        <p>arXivの論文を検索してAIで要約するアプリです</p>
    </div>
    """, unsafe_allow_html=True)

    # サイドバー設定
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # GPTモデル選択
        selected_model_name = st.selectbox(
            "GPTモデルを選択してください:",
            options=list(GPT_MODELS.keys()),
            index=0
        )
        selected_model = GPT_MODELS[selected_model_name]
        
        st.info(f"選択されたモデル: **{selected_model_name}**")
        
        st.markdown("---")
        st.markdown("### 📊 統計情報")
        if 'search_count' not in st.session_state:
            st.session_state.search_count = 0
        if 'error_count' not in st.session_state:
            st.session_state.error_count = 0
        if 'cache_hits' not in st.session_state:
            st.session_state.cache_hits = 0
            
        st.metric("検索回数", st.session_state.search_count)
        st.metric("エラー回数", st.session_state.error_count)
        st.metric("キャッシュヒット", st.session_state.cache_hits)

    # メインコンテンツ
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 検索方法選択
        st.markdown('<div class="search-method-container">', unsafe_allow_html=True)
        search_method = st.radio(
            "論文の指定方法を選択してください:",
            ["タイトルで検索", "URLまたはIDで指定"],
            horizontal=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # 入力フィールド
        if search_method == "タイトルで検索":
            paper_input = st.text_input(
                "📝 arXivの論文のタイトルを入力してください:",
                placeholder="例: Attention Is All You Need",
                help="論文の正確なタイトルを入力してください。部分一致でも検索できます。"
            )
        else:
            paper_input = st.text_input(
                "🔗 arXivのURLまたはIDを入力してください:",
                placeholder="例: https://arxiv.org/abs/1706.03762 または 1706.03762",
                help="arXivのURL、PDFリンク、またはID（1234.5678形式）を入力してください。"
            )

    with col2:
        st.markdown("### 🎯 クイックアクセス")
        st.markdown('<span class="accent-gradient">**人気の論文例:**</span>', unsafe_allow_html=True)
        
        example_papers = [
            ("Attention Is All You Need", "1706.03762"),
            ("BERT", "1810.04805"),
            ("GPT-3", "2005.14165")
        ]
        
        for title, paper_id in example_papers:
            if st.button(f"📄 {title}", key=f"example_{paper_id}"):
                st.session_state.paper_input = paper_id
                st.rerun()

    # プロンプトカスタマイズ
    with st.expander("🔧 プロンプトをカスタマイズ", expanded=False):
        custom_prompt = st.text_area(
            "システムプロンプト:",
            value=DEFAULT_PROMPT,
            height=300,
            help="論文要約のためのプロンプトを自由に編集できます"
        )
    
    # エキスパンダーが閉じている場合はデフォルトプロンプトを使用
    if 'custom_prompt' not in locals():
        custom_prompt = DEFAULT_PROMPT

    # 検索ボタン
    search_clicked = st.button(
        "🔍 論文を検索して要約", 
        type="primary",
        use_container_width=True
    )

    # セッション状態からの入力復元
    if 'paper_input' in st.session_state:
        paper_input = st.session_state.paper_input
        del st.session_state.paper_input

    # 検索実行
    if search_clicked:
        if not paper_input.strip():
            st.error("❌ 論文のタイトルまたはURLを入力してください。")
            return

        # 検索カウント更新
        st.session_state.search_count += 1

        # 論文検索
        with st.spinner("🔍 論文を検索中..."):
            if search_method == "タイトルで検索":
                result = search_paper_by_title(paper_input.strip(), apis)
            else:
                arxiv_id = apis["arxiv_search"].extract_arxiv_id_from_url(paper_input.strip())
                if not arxiv_id:
                    st.error("❌ 有効なarXiv URLまたはIDを入力してください。")
                    st.session_state.error_count += 1
                    return
                result = search_paper_by_id(arxiv_id, apis)
            
            if not result:
                st.error("❌ 該当する論文が見つかりませんでした。入力内容を確認してください。")
                st.session_state.error_count += 1
                return

        # 論文情報表示
        st.markdown('<div class="success-message">✅ 論文が見つかりました！</div>', unsafe_allow_html=True)
        display_paper_info(result)

        # 要約生成
        with st.spinner(f"🤖 {selected_model_name}で要約中..."):
            summary_text = get_summary(custom_prompt, result, selected_model, apis)
            
            if not summary_text:
                st.error("❌ 要約の生成に失敗しました。")
                st.session_state.error_count += 1
                return

            # フォーマット済みメッセージの作成
            date_str = result['published_datetime'].strftime("%Y-%m-%d %H:%M:%S")
            summary_message = f"発行日: {date_str}\n{result['entry_id']}\n{result['title']}\n\n{summary_text}\n"
            
            # セッション状態に保存（ボタンを押しても消えないように）
            st.session_state.last_result = {
                "paper_info": result,
                "summary_text": summary_text,
                "summary_message": summary_message,
                "summary_data": {
                    "title": result['title'],
                    "summary": summary_text,  # メッセージ全体ではなく要約テキストのみ
                    "url": result['entry_id'],
                    "date": result['published_datetime'].strftime("%Y-%m-%d"),
                }
            }

    # 結果表示（セッション状態から）
    if 'last_result' in st.session_state:
        result_data = st.session_state.last_result
        
        # 要約結果表示
        st.markdown("## 📋 要約結果")
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown(result_data["summary_message"])
        st.markdown('</div>', unsafe_allow_html=True)

        # アクションボタン
        st.markdown("### 📤 共有オプション")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📢 Slackに投稿", use_container_width=True, key="slack_post"):
                with st.spinner("Slackに投稿中..."):
                    message = "論文のサマリです。\n" + result_data["summary_message"]
                    success, msg = post_to_slack(message, apis)
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

        with col2:
            if st.button("📝 Notionに保存", use_container_width=True, key="notion_save"):
                with st.spinner("Notionに保存中..."):
                    success, msg = add_summary_to_notion(result_data["summary_data"], apis)
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

    # フッター
    st.markdown('<div class="footer-tips">', unsafe_allow_html=True)
    st.markdown("### 💡 使い方のヒント")
    st.markdown("""
    - **タイトル検索**: 論文のタイトルを正確に入力してください（部分一致も可能）
    - **URL/ID指定**: `https://arxiv.org/abs/1234.5678` 形式のURLまたは `1234.5678` 形式のIDが使用できます
    - **プロンプト**: 要約スタイルを変更したい場合は「プロンプトをカスタマイズ」から編集してください
    - **モデル選択**: 用途に応じてGPTモデルを選択してください
    """)
    
    st.markdown("### 🎨 このアプリについて")
    st.markdown("""
    - **<span class="accent-gradient">洗練されたデザイン</span>**: ダークモードベースの美しいUI
    - **高速検索**: キャッシュ機能により同じ検索は高速表示
    - **API連携**: Slack、Notionへの自動投稿機能
    - **エラー耐性**: 自動リトライとエラーハンドリング
    """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# メイン実行部分
if __name__ == '__main__':
    main()
