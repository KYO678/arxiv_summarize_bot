import streamlit as st
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import arxiv
import openai
from notion_client import Client
import re
import time
import random
import requests
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
                    # キャッシュファイルが破損している場合は削除
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
        openai_key = st.secrets.gptApiKey.key
        slack_token = st.secrets.SlackApiKey.key
        notion_key = st.secrets.NotionApiKey.key
        notion_db_url = st.secrets.NotionDatabaseUrl.key
        
        openai.api_key = openai_key
        notion_client = Client(auth=notion_key)
        slack_client = WebClient(token=slack_token)
        
        # 最適化されたarXivクライアント設定
        arxiv_client = arxiv.Client(
            page_size=50,           # 小さめのページサイズで安定性向上
            delay_seconds=3.0,      # arXiv推奨の3秒間隔
            num_retries=5           # 充分なリトライ回数
        )
        
        return {
            "openai_key": openai_key,
            "slack_client": slack_client,
            "notion_client": notion_client,
            "notion_db_url": notion_db_url,
            "arxiv_client": arxiv_client,
            "cache": ArxivCache()
        }
    except Exception as e:
        st.error(f"⚠️ 設定エラー: 必要なAPIキーが設定されていません。 {e}")
        st.stop()

def extract_arxiv_id_from_url(url):
    """arXiv URLからIDを抽出する"""
    try:
        # 各パターンを個別に定義
        pattern1 = r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)'
        pattern2 = r'arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)\.pdf'
        pattern3 = r'^([0-9]{4}\.[0-9]{4,5}v?[0-9]*)$'
        
        patterns = [pattern1, pattern2, pattern3]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                arxiv_id = match.group(1)
                # バージョン番号を削除
                arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
                
                # ID形式の検証
                validation_pattern = r'^[0-9]{4}\.[0-9]{4,5}$'
                if re.match(validation_pattern, arxiv_id):
                    return arxiv_id
                
        return None
    except Exception:
        return None

def robust_arxiv_search(query, max_results=5, apis=None):
    """堅牢なarXiv検索（301エラー対応）"""
    if not apis:
        return None
        
    client = apis["arxiv_client"]
    cache = apis["cache"]
    
    # キャッシュから検索
    cache_key = f"{query}_{max_results}"
    cached_results = cache.get_cached_results(cache_key, max_age_hours=6)
    if cached_results:
        st.info("🗄️ キャッシュから結果を取得しました")
        return cached_results
    
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    
    results = []
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            for result in client.results(search):
                results.append(result)
                if len(results) >= max_results:
                    break
            
            if results:
                # 成功した場合はキャッシュに保存
                cache.save_results(cache_key, results)
                return results[0] if results else None
            
            break
            
        except arxiv.UnexpectedEmptyPageError as e:
            retry_count += 1
            wait_time = (2 ** retry_count) + random.uniform(0, 1)
            st.warning(f"⚠️ arXiv APIエラー（空ページ）。{wait_time:.1f}秒後にリトライします... ({retry_count}/{max_retries})")
            time.sleep(wait_time)
            
        except arxiv.HTTPError as e:
            if hasattr(e, 'status') and e.status == 301:
                retry_count += 1
                st.warning(f"⚠️ HTTP 301リダイレクトエラー。10秒後にリトライします... ({retry_count}/{max_retries})")
                time.sleep(10)
            else:
                st.error(f"❌ HTTP エラー: {e}")
                break
                
        except Exception as e:
            error_msg = str(e)
            if "301" in error_msg:
                retry_count += 1
                st.warning(f"⚠️ リダイレクトエラー検出。{5 * retry_count}秒後にリトライします... ({retry_count}/{max_retries})")
                time.sleep(5 * retry_count)
            else:
                st.error(f"❌ 予期しないエラー: {e}")
                break
    
    return None

def search_with_semantic_scholar_fallback(query, limit=5):
    """Semantic Scholar APIを使ったフォールバック検索"""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': f"{query} arxiv",
            'limit': limit,
            'fields': 'title,abstract,authors,venue,year,externalIds,url'
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json().get('data', [])
            
            # arXiv論文をフィルタリング
            arxiv_papers = []
            for paper in data:
                external_ids = paper.get('externalIds', {})
                if external_ids and 'ArXiv' in external_ids:
                    arxiv_id = external_ids['ArXiv']
                    
                    # arXiv形式のオブジェクトを作成
                    mock_result = type('MockResult', (), {
                        'title': paper.get('title', ''),
                        'summary': paper.get('abstract', ''),
                        'entry_id': f"http://arxiv.org/abs/{arxiv_id}",
                        'published': datetime.now(),
                        'authors': [type('Author', (), {'name': author.get('name', '')})() 
                                  for author in paper.get('authors', [])]
                    })()
                    
                    arxiv_papers.append(mock_result)
            
            return arxiv_papers[0] if arxiv_papers else None
            
    except Exception as e:
        st.warning(f"⚠️ Semantic Scholar APIエラー: {e}")
        return None

def search_paper_by_title(title, apis):
    """タイトルで論文を検索（フォールバック機能付き）"""
    try:
        # まず完全一致検索を試行
        query = f'ti:"{title}"'
        result = robust_arxiv_search(query, max_results=3, apis=apis)
        
        if result:
            return result
        
        # 完全一致で見つからない場合、部分一致検索
        st.info("🔍 完全一致で見つからなかったため、部分一致検索を実行中...")
        result = robust_arxiv_search(title, max_results=5, apis=apis)
        
        if result:
            return result
        
        # arXiv APIが失敗した場合、Semantic Scholarにフォールバック
        st.warning("⚠️ arXiv検索に失敗しました。Semantic Scholar APIを試行中...")
        result = search_with_semantic_scholar_fallback(title, limit=5)
        
        if result:
            st.success("✅ Semantic Scholar経由で論文を発見しました")
            return result
        
        return None
        
    except Exception as e:
        st.error(f"❌ 論文検索エラー: {e}")
        return None

def search_paper_by_id(arxiv_id, apis):
    """arXiv IDで論文を検索（多段階検索）"""
    try:
        # まずID直接検索を試行
        search = arxiv.Search(id_list=[arxiv_id])
        result = robust_arxiv_search(f"id_list:{arxiv_id}", max_results=1, apis=apis)
        
        if result:
            return result
        
        # ID検索で見つからない場合、IDでクエリ検索を試行
        st.info("🔍 ID直接検索で見つからなかったため、クエリ検索を実行中...")
        result = robust_arxiv_search(f"id:{arxiv_id}", max_results=1, apis=apis)
        
        if result:
            return result
            
        # それでも見つからない場合、一般検索のフォールバック
        st.info("🔍 通常のクエリ検索を実行中...")
        result = robust_arxiv_search(arxiv_id, max_results=5, apis=apis)
        
        if result:
            return result
        
        # Semantic Scholar APIにフォールバック
        st.warning("⚠️ arXiv検索に失敗しました。Semantic Scholar APIを試行中...")
        result = search_with_semantic_scholar_fallback(arxiv_id, limit=5)
        
        if result:
            st.success("✅ Semantic Scholar経由で論文を発見しました")
            return result
        
        return None
        
    except Exception as e:
        st.error(f"❌ 論文取得エラー: {e}")
        return None

def get_summary(prompt, result, model, apis):
    """論文要約を生成"""
    if not prompt.strip():
        st.error("❌ プロンプトが空です。")
        return None
        
    text = f"title: {result.title}\nbody: {result.summary}"
    
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
    
    title_en = result.title
    date_str = result.published.strftime("%Y-%m-%d %H:%M:%S")
    message = f"発行日: {date_str}\n{result.entry_id}\n{title_en}\n\n{summary}\n"

    return message

def add_summary_to_notion(summary, apis):
    """Notionに要約を追加"""
    try:
        if not all(key in summary for key in ["title", "summary", "url", "date"]):
            return False, "要約データが不完全です。"
            
        if not summary["title"].strip() or not summary["summary"].strip():
            return False, "タイトルまたは要約が空です。"
            
        apis["notion_client"].pages.create(**{
            "parent": { 
                'database_id': apis["notion_db_url"]
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
        })
        return True, "成功"
    except Exception as e:
        return False, f"Notion API エラー: {e}"

def post_to_slack(message, apis):
    """Slackにメッセージを投稿"""
    try:
        if not message.strip():
            return False, "投稿するメッセージが空です。"
            
        if len(message) > 4000:
            message = message[:3900] + "\n...(省略)"
            
        response = apis["slack_client"].chat_postMessage(
            channel=SLACK_CHANNEL,
            text=message
        )
        return True, "成功"
    except SlackApiError as e:
        return False, f"Slack API エラー: {e}"
    except Exception as e:
        return False, f"Slack投稿エラー: {e}"

def display_paper_info(result):
    """論文情報を表示"""
    st.markdown('<div class="paper-info-box">', unsafe_allow_html=True)
    st.markdown("### 📄 論文情報")
    
    st.write(f"**タイトル:** {result.title}")
    st.write(f"**発行日:** {result.published.strftime('%Y-%m-%d')}")
    st.write(f"**URL:** {result.entry_id}")
    
    try:
        authors = [author.name for author in result.authors if author.name]
        if authors:
            displayed_authors = authors[:10]
            author_text = ", ".join(displayed_authors)
            if len(authors) > 10:
                author_text += f" 他 {len(authors) - 10} 名"
            st.write(f"**著者:** {author_text}")
    except Exception:
        st.write("**著者:** 情報取得できませんでした")
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    # 初期化
    apis = initialize_apis()
    
    # ヘッダー
    st.markdown("""
    <div class="main-header">
        <h1>📚 Paper Summary by ChatGPT</h1>
        <p>arXivの論文を検索してAIで要約するアプリです（arXiv API 301エラー対応版）</p>
    </div>
    """, unsafe_allow_html=True)

    # API状態情報の表示
    with st.expander("🔧 システム状態", expanded=False):
        st.markdown("### 📊 API対応状況")
        st.markdown("- ✅ **arXiv API**: 堅牢なリトライ機能付き")
        st.markdown("- ✅ **Semantic Scholar**: フォールバック対応")
        st.markdown("- ✅ **キャッシュ機能**: 6時間有効")
        st.markdown("- ✅ **HTTP 301エラー対応**: 自動リトライ")

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
        if 'fallback_count' not in st.session_state:
            st.session_state.fallback_count = 0
            
        st.metric("検索回数", st.session_state.search_count)
        st.metric("エラー回数", st.session_state.error_count)
        st.metric("フォールバック成功", st.session_state.fallback_count)

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
        with st.spinner("🔍 論文を検索中（堅牢モード）..."):
            if search_method == "タイトルで検索":
                result = search_paper_by_title(paper_input.strip(), apis)
            else:
                arxiv_id = extract_arxiv_id_from_url(paper_input.strip())
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
                "title": result.title,
                "summary": summary_message,
                "url": result.entry_id,
                "date": result.published.strftime("%Y-%m-%d"),
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
                message = "論文のサマリです。\n" + summary_message
                success, msg = post_to_slack(message, apis)
                if success:
                    st.success("✅ Slackに投稿されました！")
                else:
                    st.error(f"❌ {msg}")

        with col2:
            if st.button("📝 Notionに保存", use_container_width=True):
                success, msg = add_summary_to_notion(summary_data, apis)
                if success:
                    st.success("✅ Notionに保存されました！")
                else:
                    st.error(f"❌ {msg}")

    # フッター
    st.markdown('<div class="footer-tips">', unsafe_allow_html=True)
    st.markdown("### 💡 使い方のヒント")
    st.markdown("""
    - **arXiv API問題対応**: HTTP 301エラーに対する自動リトライ機能を搭載
    - **フォールバック機能**: arXiv APIが失敗した場合、Semantic Scholar APIを自動使用
    - **キャッシュ機能**: 同じ検索は6時間以内なら高速表示
    - **タイトル検索**: 論文のタイトルを正確に入力してください（部分一致も可能）
    - **URL/ID指定**: `https://arxiv.org/abs/1234.5678` 形式のURLまたは `1234.5678` 形式のIDが使用できます
    - **プロンプト**: 要約スタイルを変更したい場合は「プロンプトをカスタマイズ」から編集してください
    - **モデル選択**: 用途に応じてGPTモデルを選択してください（o3が最新、GPT-4.1が高性能、GPT-4.1 nanoが高速）
    """)
    
    st.markdown("### 🔧 システム改善点（v12）")
    st.markdown("""
    - **301エラー対応**: arXiv APIの2024年インフラ変更に対応した堅牢なリトライ機能
    - **Semantic Scholar統合**: arXiv検索失敗時の自動フォールバック
    - **最適化されたクライアント設定**: 3秒間隔、5回リトライで安定性向上
    - **インテリジェントキャッシュ**: 検索結果を6時間キャッシュして高速化
    - **詳細な統計情報**: 検索成功率とエラー状況をリアルタイム監視
    """)
    st.markdown('</div>', unsafe_allow_html=True)

# メイン実行部分（1箇所のみ）
if __name__ == '__main__':
    main()
