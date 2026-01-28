import streamlit as st
import whisper
import tempfile
import os
import time
import re
import requests
from datetime import timedelta
import imageio_ffmpeg
import shutil
import stat
import base64
import json
import streamlit.components.v1 as components

# --- Patch: Set ffmpeg path manually ---
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
bin_dir = os.path.join(os.getcwd(), "bin")
if not os.path.exists(bin_dir):
    os.makedirs(bin_dir)
target_ffmpeg = os.path.join(bin_dir, "ffmpeg")
if not os.path.exists(target_ffmpeg):
    shutil.copy(ffmpeg_exe, target_ffmpeg)
    st_mode = os.stat(target_ffmpeg).st_mode
    os.chmod(target_ffmpeg, st_mode | stat.S_IEXEC)
os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]

# --- Page Config ---
st.set_page_config(page_title="PodSnap", page_icon="⚡️", layout="wide", initial_sidebar_state="expanded")

# --- Global Dark Mode CSS ---
st.markdown("""
<style>
    .stApp {{ background-color: #F7F3F0 !important; }}
    [data-testid="stSidebar"] {{ background-color: #EFE9E4 !important; border-right: 1px solid #E0D6CE; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
    .stTabs [data-baseweb="tab"] {{ height: 45px; background-color: #E5DDD5; border-radius: 8px 8px 0px 0px; padding: 0px 15px; color: #7A6F66; border: none; }}
    .stTabs [aria-selected="true"] {{ background-color: #F7F3F0 !important; color: #8B5E3C !important; }}
    
    /* 1. Fix text input: Reposition hint below */
    div[data-testid="stTextInput"] [data-testid="stWidgetInstructions"],
    div[data-testid="stTextInput"] [data-testid="stInputInstructions"] {{
        position: static !important;
        display: block !important;
        margin-top: 5px !important;
        font-size: 11px !important;
        color: #8E8279 !important;
    }}
    div[data-testid="stTextInput"] > div {{
        position: relative;
    }}
    div[data-testid="stTextInput"]::after {{
        content: "↵"; /* Simple Enter Symbol */
        position: absolute;
        right: 15px;
        top: 12px;
        color: #A89B90;
        font-size: 20px;
        pointer-events: none;
    }}
    div[data-testid="stTextInput"] input {{
        height: 45px !important;
        padding: 10px 40px 10px 12px !important;
        background-color: #E5DDD5 !important;
        border: 1px solid #D1C4B9 !important;
        color: #4A3F35 !important;
    }}

    /* 2. Localize File Uploader */
    [data-testid="stFileUploader"] {{
        background-color: #E5DDD5;
        padding: 10px;
        border-radius: 10px;
        border: 1px dashed #D1C4B9;
    }}
    [data-testid="stFileUploader"] section > div > div > span {{ display: none; }}
    [data-testid="stFileUploader"] section > div > div::before {{
        content: "将音频文件拖拽至此";
        color: #A89B90;
        font-size: 14px;
        margin-bottom: 10px;
    }}
    [data-testid="stFileUploader"] button {{ text-indent: -9999px; line-height: 0; }}
    [data-testid="stFileUploader"] button::after {{
        content: "选择本地文件";
        text-indent: 0;
        display: block;
        line-height: initial;
    }}
    
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
@st.cache_resource
def load_model():
    return whisper.load_model("base")

def get_audio_base64(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

def resolve_podcast_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
        audio_match = re.search(r'https?://[^\s"\'\\]+\.(?:mp3|m4a|wav)[^\s"\'\\]*', html)
        if audio_match: return audio_match.group(0).replace('\\u002F', '/')
        return None
    except Exception as e:
        st.error(f"解析链接失败: {e}")
        return None

def download_audio(url):
    try:
        with st.spinner("正在从链接下载音频..."):
            response = requests.get(url, stream=True)
            response.raise_for_status()
            suffix = ".mp3"
            if ".m4a" in url.lower(): suffix = ".m4a"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            for chunk in response.iter_content(chunk_size=8192): tmp.write(chunk)
            tmp.close()
            return tmp.name
    except Exception as e:
        st.error(f"下载音频失败: {e}")
        return None

def get_recommendations(text):
    catalog = [
        {"keywords": ["书", "阅读", "作者", "文学"], "name": "《反脆弱》精装版", "price": "45.00", "tag": "book", "color": "#4A90E2"},
        {"keywords": ["咖啡", "提神", "拿铁", "美式"], "name": "精品挂耳咖啡", "price": "89.00", "tag": "coffee", "color": "#6F4E37"},
        {"keywords": ["抹茶", "茶", "绿茶"], "name": "宇治抹茶粉", "price": "58.00", "tag": "matcha", "color": "#77DD77"},
        {"keywords": ["科技", "手机", "电脑", "AI", "智能"], "name": "氮化镓快充头", "price": "129.00", "tag": "tech", "color": "#FFD700"},
        {"keywords": ["心理", "情绪", "压力", "健康"], "name": "冥想香薰蜡烛", "price": "168.00", "tag": "candle", "color": "#A2ADD0"}
    ]
    results = []
    for item in catalog:
        if any(kw in text for kw in item['keywords']): results.append(item)
    if len(results) < 2: results.append({"name": "PodSnap Pro 会员", "price": "19.9/月", "tag": "premium", "color": "#8B5E3C"})
    if len(results) < 3: results.append({"name": "车载手机支架", "price": "35.00", "tag": "car", "color": "#555555"})
    for item in results:
        item['img'] = f"https://images.weserv.nl/?url=loremflickr.com/200/200/{item['tag']},product/all"
    return results[:3]

# --- State Management ---
if 'transcript' not in st.session_state: st.session_state.transcript = []
if 'audio_file_path' not in st.session_state: st.session_state.audio_file_path = None
if 'model' not in st.session_state: st.session_state.model = None

# --- Sidebar: Input ---
with st.sidebar:
    st.markdown("<h1 style='color: #8B5E3C; font-size: 24px; margin-bottom: 20px;'>PodSnap ⚡️</h1>", unsafe_allow_html=True)
    tab_link, tab_local = st.tabs(["🔗 播客链接", "📁 本地文件"])
    with tab_link:
        podcast_url = st.text_input("粘贴链接", placeholder="播客分享链接...", label_visibility="collapsed", key="url_input_field")
        if podcast_url and st.button("🔍 解析并下载", use_container_width=True):
            real_audio_url = resolve_podcast_url(podcast_url)
            if real_audio_url:
                downloaded_path = download_audio(real_audio_url)
                if downloaded_path:
                    st.session_state.audio_file_path = downloaded_path
                    st.success("✅ 下载成功！")
                    st.rerun()
            else: st.error("未能嗅探到音频，请检查链接。")
    with tab_local:
        uploaded_file = st.file_uploader("上传音频", type=["mp3", "wav", "m4a"], label_visibility="collapsed", key="file_uploader_field")
        st.markdown("<p style='font-size: 11px; color: #666; margin-top: 5px; margin-left: 5px;'>支持 MP3, WAV, M4A 格式，建议文件大小不超过 100MB</p>", unsafe_allow_html=True)
        if uploaded_file and st.session_state.audio_file_path is None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
                tmp.write(uploaded_file.getvalue())
                st.session_state.audio_file_path = tmp.name
            st.success("✅ 已加载本地文件")
    if st.session_state.audio_file_path and not st.session_state.transcript:
        st.markdown("---")
        if st.button("🚀 开始 AI 转写", type="primary", use_container_width=True):
            with st.spinner("正在转写..."):
                if st.session_state.model is None: st.session_state.model = load_model()
                result = st.session_state.model.transcribe(st.session_state.audio_file_path, language="zh", initial_prompt="请使用简体中文进行转写。")
                st.session_state.transcript = result['segments']
                st.rerun()

# --- Main Interface ---
if not st.session_state.audio_file_path:
    st.title("PodSnap ⚡️")
    st.markdown("""
    <div style="color: #4A3F35; background: #EFE9E4; padding: 30px; border-radius: 15px; border: 1px solid #D1C4B9;">
    <h3 style="color: #8B5E3C;">👋 欢迎使用</h3>
    <p>每一个在播客中被触动的瞬间，都值得被珍藏。</p>
    <p>过去，你听到金句却只能任由它随风而去； 现在，PodSnap 为你实时转译，一键定格。</p>
    <ul style="line-height: 2;">
        <li>🔗 <b>全网链接，瞬时导入</b>：粘贴链接，即刻开启声音的文字之旅。</li>
        <li>🚗 <b>行驶模式，盲操记录</b>：无需分心，听到精彩处，点一下，灵感即刻入库。</li>
        <li>✨ <b>审美表达，社交裂变</b>：多种风格海报，让你的见解在朋友圈闪光。</li>
        <li>🛒 <b>内容关联，智能好物</b>：从书单到好物，播客里的推荐，触手可及。</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

elif st.session_state.audio_file_path and st.session_state.transcript:
    transcript_json = json.dumps(st.session_state.transcript)
    audio_b64 = get_audio_base64(st.session_state.audio_file_path)
    full_text = " ".join([s['text'] for s in st.session_state.transcript])
    recommendations = get_recommendations(full_text)
    recs_json = json.dumps(recommendations)
    
    html_code = f"""
    <html>
    <head>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
        <style>
            :root {{
                --bg-color: #F7F3F0;
                --card-bg: #EFE9E4;
                --text-primary: #4A3F35;
                --text-secondary: #7A6F66;
                --accent-color: #8B5E3C;
                --highlight-bg: rgba(139, 94, 60, 0.1);
            }}
            html, body {{ height: 100%; margin: 0; padding: 0; overflow: hidden; background: var(--bg-color); font-family: sans-serif; display: flex; color: var(--text-primary); }}
            #main-container {{ flex: 1; display: flex; flex-direction: column; border-right: 1px solid #D1C4B9; position: relative; }}
            #right-panel {{ width: 320px; display: flex; flex-direction: column; background: #F2EDE9; transition: width 0.3s; overflow: hidden; }}
            #right-panel.collapsed {{ width: 0; }}
            #header {{ flex: 0 0 auto; background: rgba(247, 243, 240, 0.95); padding: 15px 20px; border-bottom: 1px solid #D1C4B9; display: flex; flex-direction: column; gap: 10px; }}
            .app-title {{ font-size: 18px; font-weight: 800; color: var(--accent-color); display: flex; justify-content: space-between; align-items: center; }}
            audio {{ width: 100%; height: 35px; opacity: 0.8; }}
            #transcript {{ flex: 1; overflow-y: auto; padding: 20px; scroll-behavior: smooth; }}
            .segment {{ padding: 12px; margin-bottom: 8px; border-radius: 10px; cursor: pointer; color: var(--text-secondary); line-height: 1.5; font-size: 15px; border-left: 3px solid transparent; }}
            .segment.active {{ background-color: var(--highlight-bg); border-left: 4px solid var(--accent-color); color: var(--text-primary); font-weight: 600; transform: scale(1.01); }}
            #footer {{ flex: 0 0 auto; padding: 15px; background: var(--bg-color); border-top: 1px solid #D1C4B9; display: flex; justify-content: center; }}
            #mark-btn {{ background: var(--accent-color); color: white; border: none; width: 90%; height: 50px; border-radius: 25px; font-size: 18px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 15px rgba(139, 94, 60, 0.2); }}
            .panel-header {{ padding: 15px; font-size: 14px; font-weight: bold; color: #8E8279; border-bottom: 1px solid #D1C4B9; display: flex; justify-content: space-between; align-items: center; }}
            #records-list {{ flex: 1; overflow-y: auto; padding: 15px; }}
            .record-card {{ background: #EFE9E4; padding: 12px; border-radius: 8px; margin-bottom: 10px; cursor: pointer; border: 1px solid #D1C4B9; transition: 0.2s; }}
            .record-card:hover {{ border-color: var(--accent-color); background: #F7F3F0; }}
            .record-text {{ font-size: 13px; color: #4A3F35; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
            
            /* Product Section - Enhanced UI */
            #product-section {{ padding: 15px; background: #EFE9E4; border-top: 1px solid #D1C4B9; max-height: 280px; overflow-y: auto; }}
            .product-card {{ background: #F7F3F0; padding: 10px; border-radius: 10px; display: flex; gap: 12px; align-items: center; text-decoration: none; margin-bottom: 10px; border: 1px solid #D1C4B9; transition: 0.2s; }}
            .product-card:hover {{ border-color: var(--accent-color); }}
            .product-img-container {{ width: 50px; height: 50px; border-radius: 8px; overflow: hidden; background: #D1C4B9; flex-shrink: 0; position: relative; }}
            .product-img {{ width: 100%; height: 100%; object-fit: cover; }}
            .product-info {{ flex: 1; min-width: 0; }}
            .product-name {{ font-size: 12px; color: #4A3F35; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .product-price {{ font-size: 12px; color: var(--accent-color); margin-top: 2px; font-weight: bold; }}

            /* Modals */
            #poster-modal, #export-modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 4000; align-items: center; justify-content: center; backdrop-filter: blur(15px); }}
            #poster-wrapper, #export-wrapper {{ display: flex; flex-direction: column; align-items: center; gap: 20px; }}
            #poster-content {{ width: 320px; height: 460px; border-radius: 20px; overflow: hidden; display: flex; flex-direction: column; padding: 40px; box-sizing: border-box; position: relative; }}
            .poster-modern {{ background: #000; color: #FFF; justify-content: center; }}
            .poster-cyber {{ background: #0a0a0a; color: #0ff; justify-content: center; border: 2px solid #0ff; }}
            .poster-zen {{ background: linear-gradient(180deg, #eef2f3 0%, #8e9eab 100%); color: #2c3e50; justify-content: center; }}
            .poster-vintage {{ background: #fdfcf0; color: #4a3728; justify-content: center; border: 10px solid #e8e4c9; }}
            #poster-text {{ font-size: 22px; font-weight: bold; line-height: 1.6; z-index: 2; }}

            /* Book Style Export */
            #export-content {{ width: 360px; max-height: 80vh; background: #FFF; color: #333; padding: 40px; border-radius: 4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); overflow-y: auto; font-family: serif; position: relative; }}
            .book-title {{ font-size: 24px; font-weight: bold; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 30px; text-align: center; }}
            .book-quote {{ margin-bottom: 25px; position: relative; padding-left: 20px; border-left: 2px solid #EEE; }}
            .book-quote-text {{ font-size: 15px; line-height: 1.6; font-style: italic; }}
            .book-footer {{ margin-top: 40px; text-align: center; font-size: 12px; color: #AAA; border-top: 1px solid #EEE; padding-top: 20px; }}

            #toast {{ position: fixed; top: 80px; left: 50%; transform: translateX(-50%); background: #4CAF50; color: white; padding: 10px 20px; border-radius: 20px; font-size: 14px; display: none; z-index: 3000; }}
            .style-selector {{ display: flex; gap: 15px; background: rgba(255,255,255,0.1); padding: 12px 25px; border-radius: 40px; }}
            .style-dot {{ width: 30px; height: 30px; border-radius: 50%; border: 3px solid transparent; cursor: pointer; transition: 0.3s; }}
            .style-dot.active {{ border-color: var(--accent-color); transform: scale(1.2); }}
        </style>
    </head>
    <body>
        <div id="toast">✅ 记录成功，已存入灵感库</div>
        <div id="main-container">
            <div id="header">
                <div class="app-title"><span>PodSnap ⚡️</span><i class="fas fa-bars" style="cursor:pointer; color: #666;" onclick="togglePanel()"></i></div>
                <audio id="audio-player" controls><source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3"></audio>
            </div>
            <div id="transcript"></div>
            <div id="footer"><button id="mark-btn" onclick="captureMoment()"><i class="fas fa-bookmark"></i> 记一下</button></div>
        </div>
        <div id="right-panel">
            <div class="panel-header"><span>灵感库 <i class="fas fa-lightbulb" style="color: #FFD700;"></i></span><button onclick="openExport()" style="background:none; border:1px solid #444; color:#888; font-size:10px; padding:2px 8px; border-radius:10px; cursor:pointer;">导出全部</button></div>
            <div id="records-list"><div style="color: #444; text-align: center; margin-top: 50px; font-size: 12px;">暂无记录</div></div>
            <div id="product-section">
                <div style="font-size: 10px; color: #666; margin-bottom: 10px;">基于内容推荐</div>
                <div id="recs-container"></div>
            </div>
        </div>

        <div id="poster-modal"><div id="poster-wrapper">
            <div class="style-selector">
                <div class="style-dot active" style="background: #000;" onclick="setStyle('modern', this)"></div>
                <div class="style-dot" style="background: #0ff;" onclick="setStyle('cyber', this)"></div>
                <div class="style-dot" style="background: #8e9eab;" onclick="setStyle('zen', this)"></div>
                <div class="style-dot" style="background: #fdfcf0;" onclick="setStyle('vintage', this)"></div>
            </div>
            <div id="poster-content" class="poster-modern"><div id="poster-text"></div><div style="margin-top: 30px; font-size: 12px; opacity: 0.6;">—— 来自 PodSnap ⚡️</div></div>
            <div style="display:flex; gap:15px;">
                <button style="background: rgba(255,255,255,0.1); color: white; border: 1px solid #444; padding: 10px 25px; border-radius: 20px; font-weight: bold; cursor: pointer;" onclick="closeModal()">返回</button>
                <button style="background: var(--accent-color); color: white; border: none; padding: 10px 35px; border-radius: 20px; font-weight: bold; cursor: pointer;" onclick="downloadImage('poster-content', 'PodSnap_Poster')">保存海报</button>
            </div>
        </div></div>

        <div id="export-modal"><div id="export-wrapper">
            <div id="export-content"><div class="book-title">PodSnap 读书笔记</div><div id="book-quotes-container"></div><div class="book-footer"><div style="font-weight:bold; color:#333;">PodSnap ⚡️</div><div style="font-size:10px;">记录每一个触动瞬间</div></div></div>
            <div style="display:flex; gap:15px;">
                <button style="background: rgba(255,255,255,0.1); color: white; border: 1px solid #444; padding: 10px 25px; border-radius: 20px; font-weight: bold; cursor: pointer;" onclick="document.getElementById('export-modal').style.display='none'">返回</button>
                <button style="background: var(--accent-color); color: white; border: none; padding: 10px 35px; border-radius: 20px; font-weight: bold; cursor: pointer;" onclick="downloadImage('export-content', 'PodSnap_Notes')">分享笔记长图</button>
            </div>
        </div></div>

        <script>
            try {{
                const parentDoc = window.parent.document;
                const iframe = parentDoc.querySelector('iframe[title="streamlit.components.v1.components.html"]');
                if (iframe) {{ iframe.style.position = 'fixed'; iframe.style.top = '0'; iframe.style.left = '0'; iframe.style.width = '100vw'; iframe.style.height = '100vh'; iframe.style.zIndex = '999999'; iframe.style.border = 'none'; }}
            }} catch (e) {{}}
            const transcriptData = {transcript_json};
            const recsData = {recs_json};
            const container = document.getElementById('transcript');
            const player = document.getElementById('audio-player');
            const recordsList = document.getElementById('records-list');
            const recsContainer = document.getElementById('recs-container');
            let currentSegment = null; let records = [];
            
            // Render Recommendations with Smart Images
            recsData.forEach(item => {{
                const a = document.createElement('a'); a.className = 'product-card'; a.href = "https://s.taobao.com/search?q=" + encodeURIComponent(item.name); a.target = "_blank";
                a.innerHTML = `
                    <div class="product-img-container" style="background: ${{item.color}}">
                        <img class="product-img" src="${{item.img}}" onerror="this.style.display='none'">
                        <div style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; font-size:20px; z-index:-1">
                            ${{item.name.replace(/《|》/g, '').charAt(0)}}
                        </div>
                    </div>
                    <div class="product-info">
                        <div class="product-name">${{item.name}}</div>
                        <div class="product-price">¥ ${{item.price}}</div>
                    </div>
                    <i class="fas fa-chevron-right" style="color: #444; font-size: 10px;"></i>
                `;
                recsContainer.appendChild(a);
            }});

            transcriptData.forEach((seg, index) => {{
                const div = document.createElement('div'); div.className = 'segment'; div.id = 'seg-' + index;
                div.onclick = () => {{ player.currentTime = seg.start; player.play(); }};
                div.innerHTML = `<span style="font-size: 10px; color: #555; display: block;">${{new Date(seg.start * 1000).toISOString().substr(14, 5)}}</span>${{seg.text}}`;
                container.appendChild(div);
            }});
            player.ontimeupdate = () => {{
                const time = player.currentTime; const activeIdx = transcriptData.findIndex(seg => time >= seg.start && time < seg.end);
                if (activeIdx !== -1) {{ currentSegment = transcriptData[activeIdx]; document.querySelectorAll('.segment.active').forEach(el => el.classList.remove('active')); const activeEl = document.getElementById('seg-' + activeIdx); activeEl.classList.add('active'); activeEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }}); }}
            }};
            function captureMoment() {{ if (!currentSegment) return; records.unshift({{ ...currentSegment, timestamp: new Date().toLocaleTimeString() }}); updateRecordsUI(); showToast(); }}
            function updateRecordsUI() {{ recordsList.innerHTML = ''; records.forEach((rec, i) => {{ const div = document.createElement('div'); div.className = 'record-card'; div.onclick = () => openPoster(rec.text); div.innerHTML = `<div class="record-text">"${{rec.text}}"</div>`; recordsList.appendChild(div); }}); }}
            function showToast() {{ const t = document.getElementById('toast'); t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 2000); }}
            function togglePanel() {{ document.getElementById('right-panel').classList.toggle('collapsed'); }}
            function openPoster(text) {{ document.getElementById('poster-text').innerText = text; document.getElementById('poster-modal').style.display = 'flex'; setStyle('modern', document.querySelector('.style-dot')); }}
            function setStyle(style, el) {{ document.getElementById('poster-content').className = 'poster-' + style; document.querySelectorAll('.style-dot').forEach(d => d.classList.remove('active')); el.classList.add('active'); }}
            function closeModal() {{ document.getElementById('poster-modal').style.display = 'none'; }}
            function openExport() {{
                if (records.length === 0) {{ alert("灵感库还是空的哦"); return; }}
                const container = document.getElementById('book-quotes-container'); container.innerHTML = '';
                records.forEach(rec => {{ const div = document.createElement('div'); div.className = 'book-quote'; div.innerHTML = `<div class="book-quote-text">“${{rec.text}}”</div>`; container.appendChild(div); }});
                document.getElementById('export-modal').style.display = 'flex';
            }}
            async function downloadImage(elementId, filename) {{ const element = document.getElementById(elementId); const canvas = await html2canvas(element, {{ scale: 2 }}); const link = document.createElement('a'); link.download = filename + '.png'; link.href = canvas.toDataURL('image/png'); link.click(); }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=750, scrolling=False)
