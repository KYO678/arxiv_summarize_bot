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
    page_title="📚 Paper Summary by ChatGPT",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        margin: -1rem -1rem 2rem -1rem;
        border-radius: 0 0 15px 15px;
    }
    .main-header h1 {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .main-header p {
        font-size: 1.2rem;
        opacity: 0.9;
    }
    .search-method-container {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #e9ecef;
        margin-bottom: 1rem;
    }
    .paper-info-box {
        background: #e3f2fd;
        border: 1px solid #2196f3;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .summary-box {
        background: #f8f9fa;
        border-left: 5px solid #667eea;
        padding: 1.5rem;
        margin: 1rem 0;
        border-radius: 0 10px 10px 0;
    }
    .success-message {
        background: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-message {
        background: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-message {
        background: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .footer-tips {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.5rem;
        margin-top: 2rem;
        border: 1px solid #e9ecef;
    }
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
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
    try:
        # API キーの取得とデバッグ
        st.write("🔍 デバッグ: API初期化開始")
        
        openai_key = st.secrets.gptApiKey.key
        slack_token = st.secrets.SlackApiKey.key
        notion_key = st.secrets.NotionApiKey.key
        notion_db_url = st.secrets.NotionDatabaseUrl.key
        
        # キーの存在確認（実際の値は表示しない）
        st.write(f"- OpenAI Key: {'✅ 設定済み' if openai_key else '❌ 未設定'}")
        st.write(f"- Slack Token: {'✅ 設定済み' if slack_token else '❌ 未設定'}")
        st.write(f"- Notion Key: {'✅ 設定済み' if notion_key else '❌ 未設定'}")
        st.write(f"- Notion DB URL: {'✅ 設定済み' if notion_db_url else '❌ 未設定'}")
        
        # OpenAI初期化
        openai.api_key = openai_key
        
        # Notion初期化
        notion_client = Client(auth=notion_key)
        
        # Slack初期化
        slack_client = WebClient(token=slack_token)
        
        # 改良されたarXiv検索クライアント
        arxiv_search = ImprovedArxivSearch()
        
        # 接続テスト
        st.write("🔍 デバッグ: API接続テスト")
        
        # Slack接続テスト
        try:
            slack_test = slack_client.auth_test()
            st.write(f"- Slack: ✅ 接続成功 (User: {slack_test.get('user', 'Unknown')})")
        except Exception as e:
            st.write(f"- Slack: ❌ 接続失敗 ({str(e)})")
        
        # Notion接続テスト
        try:
            notion_test = notion_client.users.me()
            st.write(f"- Notion: ✅ 接続成功 (User: {notion_test.get('name', 'Unknown')})")
        except Exception as e:
            st.write(f"- Notion: ❌ 接続失敗 ({str(e)})")
        
        return {
            "openai_key": openai_key,
            "slack_client": slack_client,
            "notion_client": notion_client,
            "notion_db_url": notion_db_url,
            "arxiv_search": arxiv_search,
            "cache": ArxivCache()
        }
    except Exception as e:
        st.error(f"⚠️ 設定エラー: 必要なAPIキーが設定されていません。 {e}")
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
    """論文要約を生成"""
    if not prompt.strip():
        st.error("❌ プロンプトが空です。")
        return None
        
    text = f"title: {result['title']}\nbody: {result['summary']}"
    
    try:
        # 新しいOpenAI API形式
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
    except Exception as e:
        # 古いAPI形式でリトライ
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.25,
                max_tokens=2000,
            )
            summary = response["choices"][0]["message"]["content"]
        except Exception as e2:
            st.error(f"❌ OpenAI APIエラー: {e2}")
            return None
    
    if not summary:
        st.error("❌ 要約が生成されませんでした。")
        return None
    
    title_en = result['title']
    date_str = result['published_datetime'].strftime("%Y-%m-%d %H:%M:%S")
    message = f"発行日: {date_str}\n{result['entry_id']}\n{title_en}\n\n{summary}\n"

    return message

def add_summary_to_notion(summary, apis):
    """Notionに要約を追加"""
    try:
        # デバッグ情報を表示
        st.write("🔍 デバッグ: Notion連携開始")
        st.write(f"- summary keys: {list(summary.keys())}")
        st.write(f"- notion_db_url: {apis['notion_db_url']}")
        
        # データ検証
        if not all(key in summary for key in ["title", "summary", "url", "date"]):
            missing_keys = [key for key in ["title", "summary", "url", "date"] if key not in summary]
            return False, f"要約データが不完全です。不足: {missing_keys}"
            
        if not summary["title"].strip() or not summary["summary"].strip():
            return False, "タイトルまたは要約が空です。"
        
        # Notion Database IDの形式確認
        notion_db_id = apis["notion_db_url"]
        if "notion.so" in notion_db_id:
            # URLからIDを抽出
            import re
            match = re.search(r'([a-f0-9]{32})', notion_db_id)
            if match:
                notion_db_id = match.group(1)
            else:
                return False, "Notion Database URLからIDを抽出できませんでした"
        
        # ハイフンを除去
        notion_db_id = notion_db_id.replace('-', '')
        st.write(f"- 処理後のDatabase ID: {notion_db_id}")
        
        # Notionページ作成
        page_data = {
            "parent": { 
                'database_id': notion_db_id
            },
            "properties": {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": summary["title"][:100]
                            }
                        }
                    ],
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
                                "content": summary["summary"][:2000]
                            } 
                        }]
                    }
                }
            ]
        }
        
        st.write("🔍 デバッグ: Notion APIにリクエスト送信中...")
        result = apis["notion_client"].pages.create(**page_data)
        st.write(f"✅ Notion APIレスポンス: {result.get('id', 'ID不明')}")
        
        return True, "成功"
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.write(f"❌ 詳細エラー:\n```\n{error_details}\n```")
        return False, f"Notion API エラー: {str(e)}"

def post_to_slack(message, apis):
    """Slackにメッセージを投稿"""
    try:
        # デバッグ情報を表示
        st.write("🔍 デバッグ: Slack連携開始")
        st.write(f"- Channel: {SLACK_CHANNEL}")
        st.write(f"- Message length: {len(message)} characters")
        
        if not message.strip():
            return False, "投稿するメッセージが空です。"
        
        # メッセージ長制限
        if len(message) > 4000:
            message = message[:3900] + "\n...(省略)"
            st.write("⚠️ メッセージが長すぎるため省略しました")
        
        # Slack API呼び出し
        st.write("🔍 デバッグ: Slack APIにリクエスト送信中...")
        response = apis["slack_client"].chat_postMessage(
            channel=SLACK_CHANNEL,
            text=message
        )
        
        st.write(f"✅ Slack APIレスポンス: {response.get('ok', False)}")
        if response.get('ok'):
            st.write(f"- Message timestamp: {response.get('ts', 'N/A')}")
        else:
            st.write(f"- Error: {response.get('error', 'Unknown error')}")
        
        return True, "成功"
        
    except SlackApiError as e:
        st.write(f"❌ Slack API Error Code: {e.response['error']}")
        return False, f"Slack API エラー: {e.response['error']}"
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.write(f"❌ 詳細エラー:\n```\n{error_details}\n```")
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
        <p>arXivの論文を検索してAIで要約するアプリです（直接API対応版）</p>
    </div>
    """, unsafe_allow_html=True)

    # API状態情報の表示
    with st.expander("🔧 システム状態", expanded=False):
        st.markdown("### 📊 API対応状況")
        st.markdown("- ✅ **arXiv API**: 直接HTTP API経由で安定動作")
        st.markdown("- ✅ **キャッシュ機能**: 6時間有効")
        st.markdown("- ✅ **XML パース**: 確実なデータ取得")
        st.markdown("- ✅ **自動リトライ**: 接続エラー時の自動復旧")

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
        st.markdown("**人気の論文例:**")
        
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
        with st.spinner("🔍 論文を検索中（直接API経由）..."):
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
            summary_message = get_summary(custom_prompt, result, selected_model, apis)
            
            if not summary_message:
                st.error("❌ 要約の生成に失敗しました。")
                st.session_state.error_count += 1
                return

            summary_data = {
                "title": result['title'],
                "summary": summary_message,
                "url": result['entry_id'],
                "date": result['published_datetime'].strftime("%Y-%m-%d"),
            }

        # 結果表示
        st.markdown("## 📋 要約結果")
        st.markdown('<div class="summary-box">', unsafe_allow_html=True)
        st.markdown(summary_message)
        st.markdown('</div>', unsafe_allow_html=True)

        # アクションボタン
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📢 Slackに投稿", use_container_width=True):
                with st.expander("🔍 Slack投稿デバッグ情報", expanded=True):
                    message = "論文のサマリです。\n" + summary_message
                    success, msg = post_to_slack(message, apis)
                if success:
                    st.success("✅ Slackに投稿されました！")
                else:
                    st.error(f"❌ {msg}")

        with col2:
            if st.button("📝 Notionに保存", use_container_width=True):
                with st.expander("🔍 Notion保存デバッグ情報", expanded=True):
                    success, msg = add_summary_to_notion(summary_data, apis)
                if success:
                    st.success("✅ Notionに保存されました！")
                else:
                    st.error(f"❌ {msg}")

    # フッター
    st.markdown('<div class="footer-tips">', unsafe_allow_html=True)
    st.markdown("### 💡 使い方のヒント")
    st.markdown("""
    - **直接API対応**: arXiv公式APIを直接HTTP経由で呼び出すため安定動作
    - **XMLパース**: 確実なデータ取得のためのXML解析
    - **キャッシュ機能**: 同じ検索は6時間以内なら高速表示
    - **タイトル検索**: 論文のタイトルを正確に入力してください（部分一致も可能）
    - **URL/ID指定**: `https://arxiv.org/abs/1234.5678` 形式のURLまたは `1234.5678` 形式のIDが使用できます
    - **プロンプト**: 要約スタイルを変更したい場合は「プロンプトをカスタマイズ」から編集してください
    - **モデル選択**: 用途に応じてGPTモデルを選択してください（o3が最新、GPT-4.1が高性能、GPT-4.1 nanoが高速）
    """)
    
    st.markdown("### 🔧 システム改善点（v13 - 直接API版）")
    st.markdown("""
    - **直接HTTP API**: arxivライブラリを使わず、arXiv公式APIを直接呼び出し
    - **XML解析**: ElementTreeによる確実なレスポンス解析
    - **ID検索**: id_listパラメータによる正確なID検索
    - **タイトル検索**: ti:フィールドによる精密なタイトル検索とフォールバック
    - **キャッシュ最適化**: 検索結果を6時間キャッシュして高速化
    - **エラーハンドリング**: 接続エラー時の自動リトライ機能
    - **統計情報**: 検索成功率とキャッシュヒット率をリアルタイム監視
    """)
    st.markdown('</div>', unsafe_allow_html=True)

# メイン実行部分（1箇所のみ）
if __name__ == '__main__':
    main()
