# app.py
import streamlit as st
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Generator, Dict

# ==============================================================
# 1. 页面基础配置 (必须处于脚本最顶部)
# ==============================================================
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# ==============================================================
# 2. 常量与主题配置中心
# ==============================================================
THEMES = {
    "day": {
        "bg_list": [
            "linear-gradient(135deg, #f4f6f9 0%, #eef1f6 100%)",
            "linear-gradient(135deg, #fdfbf7 0%, #f5f0e6 100%)",
            "linear-gradient(135deg, #f5fbf7 0%, #eaf5ee 100%)",
            "linear-gradient(135deg, #fcf5f7 0%, #f3e6eb 100%)",
            "linear-gradient(135deg, #f6f5fa 0%, #ebe9f3 100%)",
        ],
        "mask_rgb": "248, 250, 252",
        "text_color": "#1e293b",
        "bubble_bg": "rgba(255, 255, 255, 0.95)",
        "sidebar_bg": "rgba(241, 245, 249, 0.92)"
    },
    "night": {
        "bg_list": [
            "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
            "linear-gradient(135deg, #151515 0%, #222222 100%)",
            "linear-gradient(135deg, #121824 0%, #1a2332 100%)",
            "linear-gradient(135deg, #1b1622 0%, #282132 100%)",
            "linear-gradient(135deg, #1c1917 0%, #292524 100%)",
        ],
        "mask_rgb": "15, 23, 42",
        "text_color": "#e2e8f0",
        "bubble_bg": "rgba(30, 41, 59, 0.85)",
        "sidebar_bg": "rgba(15, 23, 42, 0.9)"
    }
}

# ==============================================================
# 3. 会话状态初始化
# ==============================================================
def init_session_states():
    defaults = {
        "all_sessions": {},
        "messages": [],
        "thread_id": str(uuid.uuid4()),
        "is_login": False,
        "cookies": None,  # 持久化存储跨会话的 Cookie 凭证
        "login_fail_msg": "",
        "bg_index": 0,
        "bg_opacity": 0.65,
        "auto_read_ai": True,
        "show_setting_modal": False,
        "theme_mode": "day",
        "pending_speech": None,
        "starter_trigger": None,
        "agent_running": False,     # 智能体是否正在执行（防止追加输入冲突）
        "pending_input": None,      # 智能体执行期间用户追加的输入
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_states()

current_theme = THEMES[st.session_state.theme_mode]
bg_list = current_theme["bg_list"]
current_bg = bg_list[st.session_state.bg_index]

# ==============================================================
# 4. 工具与辅助功能区
# ==============================================================
def get_beijing_greeting() -> str:
    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    hour = beijing_time.hour
    if 5 <= hour < 9:
        return "🌅 珞珈晨曦 · 早安，今天也是元气满满的一天"
    elif 9 <= hour < 12:
        return "🍃 珞珈晴空 · 书香正浓，适合专心钻研"
    elif 12 <= hour < 14:
        return "🍚 珞珈正午 · 辛苦了，记得吃午饭并适当小憩"
    elif 14 <= hour < 18:
        return "☕ 珞珈午后 · 效率攀升，喝杯茶提提神"
    elif 18 <= hour < 23:
        return "🌌 珞珈夜阑 · 静心研读，夜里的珞珈山很温柔"
    else:
        return "🌙 珞珈深夜 · 繁星相伴，注意劳逸结合早点休息"

def speak_text(text: str):
    safe_text = text.replace("`", r"\`").replace('"', r'\"').replace("'", r"\'")
    js_script = f"""
    <script>
        window.speechSynthesis.cancel();
        const voice = new SpeechSynthesisUtterance(`{safe_text}`);
        voice.lang = "zh-CN";
        voice.rate = 1.0;
        window.speechSynthesis.speak(voice);
    </script>
    """
    st.components.v1.html(js_script, height=0)

def inject_custom_css():
    if st.session_state.theme_mode == "night":
        sidebar_button_bg = "rgba(255, 255, 255, 0.08)"
        sidebar_button_text = "#e2e8f0"
        sidebar_button_border = "1px solid rgba(255, 255, 255, 0.15)"
        sidebar_button_hover_bg = "rgba(255, 255, 255, 0.15)"
    else:
        sidebar_button_bg = "rgba(0, 0, 0, 0.05)"
        sidebar_button_text = "#1e293b"
        sidebar_button_border = "1px solid rgba(0, 0, 0, 0.1)"
        sidebar_button_hover_bg = "rgba(0, 0, 0, 0.08)"

    st.markdown(f"""
    <style>
    .stApp {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-image: {current_bg};
        background-size: cover !important;
        background-repeat: no-repeat !important;
        background-position: center center !important;
        background-attachment: fixed !important;
        z-index: -2;
        transition: background-image 0.6s ease-in-out;
    }}
    .stApp::before {{
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: rgba({current_theme['mask_rgb']}, {st.session_state.bg_opacity});
        z-index: -1;
        transition: background-color 0.6s ease-in-out;
    }}
    .main .stMarkdown, .main p, .main span, .main li, .main label {{
        color: {current_theme['text_color']} !important;
    }}
    .main h1, .main h2, .main h3, .main h4, .main h5, .main h6 {{
        color: {current_theme['text_color']} !important;
    }}
    section[data-testid="stSidebar"] .stMarkdown, 
    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span, 
    section[data-testid="stSidebar"] label {{
        color: {current_theme['text_color']} !important;
    }}
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3 {{
        color: {current_theme['text_color']} !important;
    }}
    div[data-testid="stCaptionContainer"] {{
        text-align: center;
        color: {current_theme['text_color']} !important;
    }}
    ::-webkit-scrollbar {{
        width: 6px !important;
        height: 6px !important;
    }}
    ::-webkit-scrollbar-track {{
        background: transparent !important;
    }}
    ::-webkit-scrollbar-thumb {{
        background: rgba(128, 128, 128, 0.15) !important;
        border-radius: 10px !important;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: rgba(128, 128, 128, 0.3) !important;
    }}
    section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) {{
        background-color: {sidebar_button_bg} !important;
        border: {sidebar_button_border} !important;
        transition: background-color 0.2s ease, border-color 0.2s ease;
    }}
    section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) p,
    section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="baseButton-primary"]) span {{
        color: {sidebar_button_text} !important;
    }}
    section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="baseButton-primary"]):hover {{
        background-color: {sidebar_button_hover_bg} !important;
    }}
    .stChatMessage {{
        background: {current_theme['bubble_bg']} !important;
        border-radius: 12px !important;
        transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s ease !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
    }}
    .stChatMessage:hover {{
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.05) !important;
    }}
    section[data-testid="stSidebar"] {{
        background: transparent !important;
    }}
    section[data-testid="stSidebar"] .stVerticalBlock {{
        background: {current_theme['sidebar_bg']};
        padding: 12px;
        border-radius: 10px;
    }}
    section[data-testid="stSidebar"] div[data-testid="stPopover"] button {{
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        background: transparent !important;
        border-radius: 6px !important;
        height: 100% !important;
    }}
    div[data-testid="stChatInput"] {{
        border-radius: 18px !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.08) !important;
    }}
    div[data-testid="stChatInput"] textarea {{
        border-radius: 18px !important;
        padding: 12px 16px !important;
        border: 1px solid #e0e7ff !important;
        background: rgba(255,255,255,0.1);
        color: {current_theme['text_color']} !important;
    }}
    .stChatMessage div[data-testid="stHorizontalBlock"] {{
        justify-content: flex-end;
    }}
    
    /* ==============================================================
       修改：更进一步提升提示词的高度 (bottom: 155px)
       并引入响应式 CSS，自动根据侧边栏展开/收起状态调整左右定位，使其完美相对于主栏居中
       ============================================================== */
    .st-key-starter_container {{
        position: fixed !important;
        bottom: 155px !important;
        left: calc(50% + 128px) !important; /* 默认主栏居中 (视口中点 + 默认侧边栏宽度 256px 的一半) */
        transform: translateX(-50%) !important;
        width: calc(100% - 40px) !important;
        max-width: 730px !important;
        z-index: 999998 !important;
        background: transparent !important;
        transition: left 0.25s ease-in-out !important; /* 当侧边栏状态切换时平滑移动 */
    }}
    
    /* 当左侧侧边栏折叠 (aria-expanded="false") 时，主栏将占满整个视口，因此按钮回归 50% 屏幕正中 */
    [data-testid="stSidebar"][aria-expanded="false"] ~ .main .st-key-starter_container {{
        left: 50% !important;
    }}
    
    /* 移动端/小屏幕适配：侧边栏通常采用悬浮蒙层，主栏并不被实际往右推挤，因此回归 50% 屏幕正中 */
    @media (max-width: 991.98px) {{
        .st-key-starter_container {{
            left: 50% !important;
        }}
    }}

    .st-key-starter_container button {{
        background-color: {current_theme['bubble_bg']} !important;
        color: {current_theme['text_color']} !important;
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04) !important;
        transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.2s ease, border-color 0.2s ease !important;
        font-size: 11px !important;
    }}
    .st-key-starter_container button:hover {{
        transform: translateY(-2px) !important;
        border-color: #00a4ff !important;
    }}
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ==============================================================
# 趣味话语排版
# ==============================================================
def render_fun_quotes(text_color: str):
    quotes = [
        "今天又是被高数‘教做人’的一天吗？🧠",
        "文理学部的樱花开了，但我的代码还没跑通……🌸",
        "信息学部的外卖，今天又是在哪个栅栏处接头？🚲",
        "去图书馆抢座的速度，决定了我本学期的绩点。🏃‍♂️",
        "今天吃工学部食堂，还是去梅园凑合一下？🍚",
        "听说，在珞珈山散步容易偶遇到野猪？🐗",
        "弘毅学堂的学霸，连梦话都是在背单词。📖",
        "我的绩点就像珞珈山的台阶，爬得我气喘吁吁。🧗‍♂️",
        "今天的天气，适合去东湖骑行，不适合写代码.🚴",
        "万物皆可LuojiaAgent，除了帮我写作业。😜",
        "梅园的台阶、樱顶的楼梯，珞珈山每天都在帮我做有氧。🏃‍♀️",
        "只要胆子大，九一二操场也是我的停机坪。✈️",
        "听说，每个武大人的青春里，都有一只叫‘珞珞’或‘珈珈’的猫。🐱",
        "桂园的食堂、工学部的菜，今天该翻谁的牌？🍱"
    ]
    
    quotes_js_array = json.dumps(quotes, ensure_ascii=False)
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    body {{
        margin: 0;
        padding: 0;
        background: transparent;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        overflow: hidden;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 55px;
    }}
    .quote-container {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: rgba(128, 128, 128, 0.05);
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.12);
        max-width: 95%;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .quote-text {{
        font-size: 10px;
        color: {text_color};
        opacity: 0.8;
        transition: opacity 0.25s ease, transform 0.25s ease;
        white-space: normal;
        word-break: break-all;
        line-height: 1.3;
        user-select: none;
    }}
    .refresh-btn {{
        flex-shrink: 0;
        background: none;
        border: none;
        cursor: pointer;
        font-size: 10px;
        padding: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.4s ease;
        outline: none;
        opacity: 0.6;
    }}
    .refresh-btn:hover {{
        opacity: 1;
        transform: scale(1.15);
    }}
    .refresh-btn.rotating {{
        transform: rotate(360deg);
    }}
    .fade-out {{
        opacity: 0 !important;
        transform: translateY(-3px);
    }}
    .fade-in {{
        opacity: 0.8 !important;
        transform: translateY(0);
    }}
    </style>
    </head>
    <body>
    <div class="quote-container">
        <span id="quote-text" class="quote-text">...</span>
        <button id="refresh-btn" class="refresh-btn" title="换一句">🔄</button>
    </div>
    
    <script>
    const quotes = {quotes_js_array};
    const quoteText = document.getElementById('quote-text');
    const refreshBtn = document.getElementById('refresh-btn');

    function getRandomQuote() {{
        const idx = Math.floor(Math.random() * quotes.length);
        return quotes[idx];
    }}

    quoteText.textContent = getRandomQuote();

    refreshBtn.addEventListener('click', () => {{
        refreshBtn.classList.add('rotating');
        setTimeout(() => refreshBtn.classList.remove('rotating'), 400);

        quoteText.classList.remove('fade-in');
        quoteText.classList.add('fade-out');

        setTimeout(() => {{
            let newQuote = getRandomQuote();
            while (newQuote === quoteText.textContent && quotes.length > 1) {{
                newQuote = getRandomQuote();
            }}
            quoteText.textContent = newQuote;
            
            quoteText.classList.remove('fade-out');
            quoteText.classList.add('fade-in');
        }}, 250);
    }});
    </script>
    </body>
    </html>
    """
    st.components.v1.html(html_code, height=55)

# ==============================================================
# 5. 模态设置面板 (Dialog)
# ==============================================================
def reset_setting_modal():
    st.session_state.show_setting_modal = False

@st.dialog("系统设置面板", width="small", on_dismiss=reset_setting_modal)
def render_setting_modal():
    st.subheader("🌓 显示模式")
    
    is_night = st.session_state.theme_mode == "night"
    theme_toggle = st.toggle(
        "开启低蓝光夜间模式 (关闭为护眼日间模式)", 
        value=is_night,
        help="开启后切换为柔和低光slate暗色调；关闭则恢复为高清晰暖光日间调色"
    )
    
    new_mode = "night" if theme_toggle else "day"
    if new_mode != st.session_state.theme_mode:
        st.session_state.theme_mode = new_mode
        st.rerun()

    st.divider()
    st.subheader("🖼️ 背景设置")
    new_opacity = st.slider(
        "背景淡化透明度",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        value=st.session_state.bg_opacity,
        help="数值越大遮罩越浅；数值越小背景原图越清晰"
    )
    if new_opacity != st.session_state.bg_opacity:
        st.session_state.bg_opacity = new_opacity
        st.rerun()

    if st.button("切换内置背景", use_container_width=True):
        st.session_state.bg_index = (st.session_state.bg_index + 1) % len(bg_list)
        st.rerun()

    st.divider()
    st.subheader("🔊 朗读设置")
    st.checkbox(
        "AI回复完成后自动朗读",
        value=st.session_state.auto_read_ai,
        key="auto_read_ai",
        help="开启后AI回答生成完毕自动朗读全文"
    )
    st.divider()
    if st.button("关闭设置", type="secondary", use_container_width=True):
        st.session_state.show_setting_modal = False
        st.rerun()

# ==============================================================
# 6. 侧边栏渲染 (Sidebar)
# ==============================================================
def render_sidebar():
    with st.sidebar:
        greeting_text = get_beijing_greeting()
        st.markdown(
            f"""
            <div style="
                background: rgba(128, 128, 128, 0.08); 
                padding: 10px 14px; 
                border-radius: 8px; 
                border-left: 3px solid #00a4ff; 
                margin-bottom: 15px;
            ">
                <p style="
                    margin: 0; 
                    font-size: 11px; 
                    letter-spacing: 0.5px; 
                    line-height: 1.5; 
                    color: {current_theme['text_color']};
                    opacity: 0.9;
                ">
                    {greeting_text}
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.subheader("账号状态")
        if st.session_state.login_fail_msg:
            st.error(st.session_state.login_fail_msg)

        if not st.session_state.is_login:
            login_method = st.radio("登录方式",
                ["🔑 密码登录", "📱 扫码登录", "🌐 浏览器弹窗"],
                horizontal=True, label_visibility="collapsed")

            if login_method == "🔑 密码登录":
                with st.form("pwd_login"):
                    user = st.text_input("学号", placeholder="2025302114221")
                    pwd = st.text_input("密码", type="password", placeholder="CAS 密码")
                    submitted = st.form_submit_button("登录", use_container_width=True, type="primary")
                    if submitted and user and pwd:
                        st.session_state.login_fail_msg = ""
                        try:
                            from tools.cas_login import CasClient
                            from tools.login_helper import harvest_from_castgc
                            with st.status("正在登录...", expanded=True) as s:
                                s.write("CAS 认证中...")
                                client = CasClient()
                                castgc = client.login_password(user, pwd)
                                if not castgc:
                                    st.session_state.login_fail_msg = "登录失败，请检查学号和密码"
                                    s.update(label="❌ 登录失败", state="error", expanded=True)
                                else:
                                    s.write("正在获取图书馆和教务凭证...")
                                    result = harvest_from_castgc(castgc)
                                    st.session_state.cookies = {
                                        "castgc": castgc,
                                        "educational": result.get("educational", ""),
                                        "library_token": result.get("library_token", ""),
                                        "library_hmac_key": result.get("library_hmac_key", ""),
                                        "library_cookie": result.get("library_cookie", []),
                                    }
                                    st.session_state.is_login = True
                                    s.update(label="✅ 登录完成", state="complete", expanded=False)
                                    st.rerun()
                        except Exception as e:
                            st.session_state.login_fail_msg = f"登录异常：{e}"

            elif login_method == "📱 扫码登录":
                if "qr_client" not in st.session_state:
                    from tools.cas_login import CasClient
                    st.session_state.qr_client = CasClient()
                qr = st.session_state.qr_client

                if "qr_img" not in st.session_state:
                    try:
                        img = qr.qr_get_image()
                        if img:
                            st.session_state.qr_img = img
                        else:
                            st.error("获取二维码失败，请重试")
                    except Exception as e:
                        st.error(f"获取二维码失败：{e}")

                if st.session_state.get("qr_img"):
                    import base64
                    st.image(base64.b64decode(st.session_state.qr_img), caption="手机扫码登录", width=200)

                if st.button("已扫码，完成登录", use_container_width=True, type="primary"):
                    try:
                        from tools.login_helper import harvest_from_castgc
                        with st.status("正在等待确认...", expanded=True) as s:
                            castgc = qr.qr_poll(timeout=10)
                            if not castgc:
                                s.update(label="❌ 未检测到确认，请重试", state="error", expanded=True)
                            else:
                                s.write("正在获取图书馆和教务凭证...")
                                result = harvest_from_castgc(castgc)
                                st.session_state.cookies = {
                                    "castgc": castgc,
                                    "educational": result.get("educational", ""),
                                    "library_token": result.get("library_token", ""),
                                    "library_hmac_key": result.get("library_hmac_key", ""),
                                    "library_cookie": result.get("library_cookie", []),
                                }
                                st.session_state.is_login = True
                                del st.session_state.qr_client
                                del st.session_state.qr_img
                                s.update(label="✅ 登录完成", state="complete", expanded=False)
                                st.rerun()
                    except Exception as e:
                        st.error(f"登录异常：{e}")

                if st.button("刷新二维码", use_container_width=True):
                    st.session_state.qr_client = None
                    st.session_state.qr_img = None
                    st.rerun()

            else:
                login_btn = st.button("🔐 唤起浏览器登录", use_container_width=True, type="primary")
                if login_btn:
                    st.session_state.login_fail_msg = ""
                    try:
                        from agent import run_agent_stream, get_agent_cookies
                        login_generator = run_agent_stream(
                            user_input="调用统一身份登录工具完成登录",
                            thread_id=st.session_state.thread_id,
                            student_id="",
                            password=""
                        )
                        with st.status("正在唤起浏览器登录窗口...", expanded=True) as login_status:
                            login_success = False
                            for event in login_generator:
                                event_type = event.get("type")
                                content = event.get("content", "")
                                login_status.write(content)
                                if event_type == "tool_output":
                                    login_success = True
                            if login_success:
                                cookies = get_agent_cookies(st.session_state.thread_id)
                                if cookies:
                                    st.session_state.cookies = cookies
                                    st.session_state.is_login = True
                                    login_status.update(label="✅ 登录完成", state="complete", expanded=False)
                                else:
                                    st.session_state.login_fail_msg = "未检测到成功的会话凭证，请重试。"
                                    login_status.update(label="❌ 登录失败", state="error", expanded=True)
                            else:
                                st.session_state.login_fail_msg = "未完成浏览器登录验证，请重试"
                                login_status.update(label="❌ 登录失败", state="error", expanded=True)
                    except Exception as e:
                        st.session_state.login_fail_msg = f"登录异常：{str(e)}"
                    st.rerun()
        else:
            logout_btn = st.button("✅ 已登录 | 点击退出登录", use_container_width=True, type="secondary")
            if logout_btn:
                st.session_state.is_login = False
                st.session_state.cookies = None  # 清除持久化的凭证
                st.session_state.login_fail_msg = ""
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.messages = []
                st.rerun()

        st.divider()
        st.subheader("💬 快捷操作")
        if st.button("🗑️ 清空当前聊天", use_container_width=True, type="secondary"):
            st.session_state.messages = []
            st.rerun()
            
        if st.button("🔄 新建对话会话", use_container_width=True, type="primary"):
            if len(st.session_state.messages) > 0:
                first_user_msg = next(
                    (m["content"] for m in st.session_state.messages if m["role"] == "user"),
                    "空白对话"
                )
                session_title = first_user_msg[:20] + "..." if len(first_user_msg) > 20 else first_user_msg
                st.session_state.all_sessions[st.session_state.thread_id] = {
                    "title": session_title,
                    "messages": st.session_state.messages.copy()
                }
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()

        st.divider()
        st.header("📚 历史对话存档")
        st.divider()
        
        current_tid = st.session_state.thread_id
        session_items = list(st.session_state.all_sessions.items())
        
        if not session_items:
            st.info("暂无存档\n新建对话后自动保存")
        else:
            for tid, info in reversed(session_items):
                title = info["title"]
                msg_count = len(info["messages"])
                btn_label = f"🟢 {title} ({msg_count}条)" if tid == current_tid else f"📄 {title} ({msg_count}条)"
                btn_type = "primary" if tid == current_tid else "secondary"
                
                btn_col1, btn_col2 = st.columns([0.82, 0.18], vertical_alignment="center")
                with btn_col1:
                    if st.button(btn_label, type=btn_type, use_container_width=True, key=f"switch_{tid}"):
                        st.session_state.thread_id = tid
                        st.session_state.messages = info["messages"].copy()
                        st.rerun()
                with btn_col2:
                    with st.popover("⋮", use_container_width=True, help="会话管理选项"):
                        st.write("📂 历史会话管理")
                        if st.button("🗑️ 删除此对话", key=f"del_{tid}", use_container_width=True, type="primary"):
                            del st.session_state.all_sessions[tid]
                            if tid == current_tid:
                                st.session_state.messages = []
                                st.session_state.thread_id = str(uuid.uuid4())
                            st.rerun()
                            
        st.divider()
        if st.button("🧹 清空所有存档", use_container_width=True):
            st.session_state.all_sessions = {}
            st.rerun()

        # 随机有趣话语放置在侧边栏底部
        st.divider()
        render_fun_quotes(current_theme['text_color'])

# ==============================================================
# 7. 页面头部渲染
# ==============================================================
header_row = st.columns([0.15, 0.7, 0.15], vertical_alignment="center")
with header_row[1]:
    st.markdown(
        f"<h1 style='text-align: center; margin: 0; padding: 0; color: {current_theme['text_color']};'>🏫 LuojiaAgent 智能校园助手</h1>", 
        unsafe_allow_html=True
    )
    st.markdown(
        f"<p style='text-align: center; margin: 8px 0 0 0; font-size: 0.95rem; color: {current_theme['text_color']}; opacity: 0.85;'>基于 DeepSeek 与 LangGraph 构建 of 武大校园助手系统</p>", 
        unsafe_allow_html=True
    )
with header_row[2]:
    setting_btn = st.button("⚙️ 设置", use_container_width=True, help="打开背景/朗读/显示模式设置面板")
    if setting_btn:
        st.session_state.show_setting_modal = True
        st.rerun()

if st.session_state.show_setting_modal:
    render_setting_modal()

render_sidebar()

# ==============================================================
# 8. 主聊天区域与逻辑控制
# ==============================================================
chat_container = st.container(height=600)
with chat_container:
    if len(st.session_state.messages) == 0:
        st.markdown(
            f"""
            <div style="text-align: center; margin-top: 100px; margin-bottom: 20px; opacity: 0.85;">
                <span style="font-size: 50px; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));">🏫</span>
                <h3 style="margin-top: 15px; font-weight: 600; color: {current_theme['text_color']};">你好！我是你的 LuojiaAgent</h3>
                <p style="font-size: 13px; color: {current_theme['text_color']}; opacity: 0.7;">
                    我是你的专属珞珈智能助手。点击下方固定快捷按钮，或在输入框中直接提问，即可开始与我交流！
                </p>
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        for msg_idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                col_text, col_audio = st.columns([0.92, 0.08], vertical_alignment="center")
                with col_audio:
                    if st.button("🔊", key=f"read_msg_{msg_idx}", help="朗读本条文本", use_container_width=True):
                        speak_text(msg["content"])

# 检查并在页面主渲染结束后播报语音
if st.session_state.pending_speech:
    speak_text(st.session_state.pending_speech)
    st.session_state.pending_speech = None

# 固定在输入框上方悬浮的 4 个紧凑辅助功能按钮
with st.container(key="starter_container"):
    button_cols = st.columns(4)
    starters = [
        ("📅 课程表查询", "帮我查一下明天的课程安排"),
        ("📚 图书馆空座", "帮我看看现在图书馆哪里有空座"),
        ("🌤️ 校园天气", "今天武大校园的天气怎么样"),
        ("📈 成绩查询", "帮我查询一下我的期末成绩")
    ]
    for idx, (label, query) in enumerate(starters):
        with button_cols[idx]:
            if st.button(label, use_container_width=True, key=f"fixed_starter_{idx}", help=f"发送指令: '{query}'"):
                st.session_state.starter_trigger = query
                st.rerun()

triggered_input = st.session_state.get("starter_trigger", None)
if triggered_input:
    user_input = triggered_input
    st.session_state.starter_trigger = None
else:
    user_input = st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)")

if user_input:
    user_input = user_input.strip()
    if user_input == "":
        st.warning("请输入有效提问内容")
        st.stop()
        
    if not st.session_state.is_login:
        st.error("当前未登录，请先点击左侧侧边栏【🔐 点击登录】完成统一身份认证！")
        st.stop()

    # 1. 用户提问上屏与记录
    st.session_state.messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)
            col_text, col_audio = st.columns([0.92, 0.08], vertical_alignment="center")
            with col_audio:
                new_msg_idx = len(st.session_state.messages) - 1
                if st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本", use_container_width=True):
                    speak_text(user_input)

    # 2. 助手流式交互及工具调用反馈
    accumulated_answer = ""
    with chat_container:
        with st.chat_message("assistant"):
            status_container = st.status("🔍 智能体正在规划与执行...", expanded=True)
            response_placeholder = st.empty()
            
            try:
                from agent import run_agent_stream
                event_generator: Generator[Dict, None, None] = run_agent_stream(
                    user_input=user_input,
                    thread_id=st.session_state.thread_id,
                    student_id="",
                    password="",
                    cookies=st.session_state.cookies  # 将持久化保存的 cookies 注入到新会话状态
                )
                
                with status_container:
                    for event in event_generator:
                        event_type = event.get("type")
                        content = event.get("content", "")
                        
                        if event_type == "tool_start":
                            st.markdown(f"🧠 **思考决策**\n> {content}")
                        elif event_type == "tool_output":
                            if content.startswith("📥 工具执行成功"):
                                st.markdown(f"📥 **工具反馈数据**")
                                st.info(content)
                            else:
                                status_container.update(label="✅ 规划与工具调用执行完毕", state="complete", expanded=False)
                                accumulated_answer = content
                                response_placeholder.markdown(accumulated_answer)
                        elif event_type == "final_answer":
                            status_container.update(label="✅ 规划与工具调用执行完毕", state="complete", expanded=False)
                            accumulated_answer = content
                            response_placeholder.markdown(accumulated_answer)
            except Exception as e:
                status_container.update(label="❌ 执行过程中出现异常", state="error", expanded=True)
                accumulated_answer = f"系统调用异常：{str(e)}"
                response_placeholder.markdown(accumulated_answer)
                
            col_text, col_audio = st.columns([0.92, 0.08], vertical_alignment="center")
            with col_audio:
                new_msg_idx = len(st.session_state.messages)
                if st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本", use_container_width=True):
                    speak_text(accumulated_answer)
                    
    # 3. 结果保存与语音播报配置，并触发一次整洁的 Rerun 进行状态同步
    st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})
    if st.session_state.auto_read_ai and accumulated_answer.strip():
        st.session_state.pending_speech = accumulated_answer
        
    st.rerun()
