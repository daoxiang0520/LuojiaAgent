# app.py
import streamlit as st
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Generator, Dict

# ==============================================================================
# 1. 页面基础配置 (必须处于脚本最顶部)
# ==============================================================================
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# ==============================================================================
# 2. 常量与主题配置中心 (已对色彩深度调优，极致护眼)
# ==============================================================================
THEMES = {
    "day": {
        "bg_list": [
            "linear-gradient(135deg, #f4f6f9 0%, #eef1f6 100%)",  # 柔和冰蓝灰
            "linear-gradient(135deg, #fdfbf7 0%, #f5f0e6 100%)",  # 暖纸色 (极度舒适)
            "linear-gradient(135deg, #f5fbf7 0%, #eaf5ee 100%)",  # 淡雅薄荷
            "linear-gradient(135deg, #fcf5f7 0%, #f3e6eb 100%)",  # 晚樱粉白
            "linear-gradient(135deg, #f6f5fa 0%, #ebe9f3 100%)",  # 软紫罗兰
        ],
        "mask_rgb": "248, 250, 252",  # Slate-50 舒适底色
        "text_color": "#1e293b",      # Slate-800 代替纯黑，柔和对比
        "bubble_bg": "rgba(255, 255, 255, 0.95)",
        "sidebar_bg": "rgba(241, 245, 249, 0.92)"
    },
    "night": {
        "bg_list": [
            "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",  # 深灰石板色 (主打)
            "linear-gradient(135deg, #151515 0%, #222222 100%)",  # 暖灰黑 (无眩光)
            "linear-gradient(135deg, #121824 0%, #1a2332 100%)",  # 科技暗蓝
            "linear-gradient(135deg, #1b1622 0%, #282132 100%)",  # 极低蓝光暖紫
            "linear-gradient(135deg, #1c1917 0%, #292524 100%)",  # 暖石墨色
        ],
        "mask_rgb": "15, 23, 42",      # Slate-900 绝佳滤光底色
        "text_color": "#e2e8f0",      # Slate-200 柔和灰白，有效防止眼球Halo效应
        "bubble_bg": "rgba(30, 41, 59, 0.85)", # Slate-800 半透气泡
        "sidebar_bg": "rgba(15, 23, 42, 0.9)"
    }
}

# ==============================================================================
# 3. 会话状态初始化
# ==============================================================================
def init_session_states():
    defaults = {
        "all_sessions": {},
        "messages": [],
        "thread_id": str(uuid.uuid4()),
        "is_login": False,
        "login_fail_msg": "",
        "bg_index": 0,
        "bg_opacity": 0.65,
        "auto_read_ai": True,
        "show_setting_modal": False,
        "theme_mode": "day",
        "pending_speech": None,  # 用于记录当前需要朗读的文本，防止 rerun 中断语音播报
        "starter_trigger": None  # 用于记录推荐卡片点击触发提问的临时变量
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_states()

# 根据当前主题读取配置
current_theme = THEMES[st.session_state.theme_mode]
bg_list = current_theme["bg_list"]
current_bg = bg_list[st.session_state.bg_index]

# ==============================================================================
# 4. 工具与辅助功能区
# ==============================================================================
def get_beijing_greeting() -> str:
    """根据东八区物理时间返回具有珞珈校园气息的迎宾语"""
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
    """通过系统 SpeechSynthesis 接口朗读文本"""
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
    """动态注入 CSS 样式以支持主题切换、精细滚动条、气泡动效及位置适配"""
    
    # 针对不同主题动态计算侧边栏普通按钮（非高亮 Primary 按钮）的颜色配置，确保高对比度
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
    /* 全局背景过渡动画 */
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
    /* 遮罩层过渡 */
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
    /* 主界面文字颜色自适应 */
    .main .stMarkdown, .main p, .main span, .main li, .main label {{
        color: {current_theme['text_color']} !important;
    }}
    .main h1, .main h2, .main h3, .main h4, .main h5, .main h6 {{
        color: {current_theme['text_color']} !important;
    }}
    /* 侧边栏文字颜色自适应 */
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

    /* 极致美化全局滚动条，使之极细且透明，不遮挡精美背景 */
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

    /* 强制重塑侧边栏次要按钮的背景色和字色，防亮色环境污染 */
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

    /* 气泡样式自适应与悬浮微升呼吸感动画 */
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

    /* 侧边栏布局调优 */
    section[data-testid="stSidebar"] {{
        background: transparent !important;
    }}
    section[data-testid="stSidebar"] .stVerticalBlock {{
        background: {current_theme['sidebar_bg']};
        padding: 12px;
        border-radius: 10px;
    }}
    /* 侧边栏三点操作按钮微调 */
    section[data-testid="stSidebar"] div[data-testid="stPopover"] button {{
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        background: transparent !important;
        border-radius: 6px !important;
        height: 100% !important;
    }}
    /* 聊天输入框美化 */
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

    /* 趣味句子组件外壳固定定位：放置在屏幕最底部中央输入框下方 */
    .custom-quote-wrapper {{
        position: fixed;
        bottom: 5px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 99999;
        width: 100%;
        max-width: 600px;
        text-align: center;
        pointer-events: auto;
    }}
    
    /* 稍许抬高输入框高度，为底部趣味句子腾出精致空隙 */
    div[data-testid="stChatInput"] {{
        margin-bottom: 24px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

def render_fun_quotes(text_color: str):
    """渲染底部随机趣味段子组件（内含纯前端无延迟淡入淡出动画及旋转重置）"""
    quotes = [
        "今天又是被高数‘教做人’的一天吗？🧠",
        "文理学部的樱花开了，但我的代码还没跑通……🌸",
        "信息学部的外卖，今天又是在哪个栅栏处接头？🚲",
        "去图书馆抢座的速度，决定了我本学期的绩点。🏃‍♂️",
        "今天吃工学部食堂，还是去梅园凑合一下？🍚",
        "听说，在珞珈山散步容易偶遇到野猪？🐗",
        "弘毅学堂的学霸，连梦话都是在背单词。📖",
        "我的绩点就像珞珈山的台阶，爬得我气喘吁吁。🧗‍♂️",
        "今天的天气，适合去东湖骑行，不适合写代码。🚴",
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
        height: 35px;
    }}
    .quote-container {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 3px 10px;
        background: rgba(128, 128, 128, 0.05);
        border-radius: 20px;
        border: 1px solid rgba(128, 128, 128, 0.12);
        max-width: 95%;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .quote-text {{
        font-size: 11px;
        color: {text_color};
        opacity: 0.8;
        transition: opacity 0.25s ease, transform 0.25s ease;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        user-select: none;
    }}
    .refresh-btn {{
        background: none;
        border: none;
        cursor: pointer;
        font-size: 11px;
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
    st.markdown('<div class="custom-quote-wrapper">', unsafe_allow_html=True)
    st.components.v1.html(html_code, height=35)
    st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 5. 模态设置面板 (Dialog)
# ==============================================================================
def reset_setting_modal():
    """当用户通过点击外部、按 ESC 键或右上角 X 键关闭设置弹窗时，清除状态标志"""
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

# ==============================================================================
# 6. 侧边栏渲染 (Sidebar)
# ==============================================================================
def render_sidebar():
    with st.sidebar:
        # 融入武大专属时辰人文卡片
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
            login_btn = st.button("🔐 点击登录", use_container_width=True, type="primary")
            if login_btn:
                st.session_state.login_fail_msg = ""
                try:
                    from agent import run_agent_stream
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
                            st.session_state.is_login = True
                            login_status.update(label="✅ 登录完成", state="complete", expanded=False)
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

# ==============================================================================
# 7. 页面头部渲染 (采用三栏布局，实现大标题水平居中)
# ==============================================================================
header_row = st.columns([0.15, 0.7, 0.15], vertical_alignment="center")
with header_row[1]:
    st.markdown(
        f"<h1 style='text-align: center; margin: 0; padding: 0; color: {current_theme['text_color']};'>🏫 LuojiaAgent 智能校园助手</h1>", 
        unsafe_allow_html=True
    )
    st.markdown(
        f"<p style='text-align: center; margin: 8px 0 0 0; font-size: 0.95rem; color: {current_theme['text_color']}; opacity: 0.85;'>基于 DeepSeek 与 LangGraph 构建的武大校园助手系统</p>", 
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

# ==============================================================================
# 8. 主聊天区域与逻辑控制 (Main Interface)
# ==============================================================================
chat_container = st.container(height=600)
with chat_container:
    # 渲染历史保存下来的对话消息。若无历史，则呈现精美的珞珈灵感卡片。
    if len(st.session_state.messages) == 0:
        st.markdown(
            f"""
            <div style="text-align: center; margin-top: 60px; margin-bottom: 20px; opacity: 0.85;">
                <span style="font-size: 50px; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));">🏫</span>
                <h3 style="margin-top: 15px; font-weight: 600; color: {current_theme['text_color']};">你好！我是你的 LuojiaAgent</h3>
                <p style="font-size: 13px; color: {current_theme['text_color']}; opacity: 0.7;">
                    你可以向我查询课表、预约座位、查询成绩或了解天气。尝试点击下方卡片开启对话：
                </p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        col1, col2 = st.columns(2)
        starters = [
            ("📅 查明天的课程表", "帮我查一下明天的课程安排"),
            ("📚 查询图书馆空座", "帮我看看现在图书馆哪里有空座"),
            ("🌤️ 校园天气预测", "今天武大校园的天气怎么样"),
            ("📈 查询本学期成绩", "帮我查询一下我的期末成绩")
        ]
        with col1:
            if st.button(starters[0][0], use_container_width=True, key="star1"):
                st.session_state.starter_trigger = starters[0][1]
                st.rerun()
            if st.button(starters[1][0], use_container_width=True, key="star2"):
                st.session_state.starter_trigger = starters[1][1]
                st.rerun()
        with col2:
            if st.button(starters[2][0], use_container_width=True, key="star3"):
                st.session_state.starter_trigger = starters[2][1]
                st.rerun()
            if st.button(starters[3][0], use_container_width=True, key="star4"):
                st.session_state.starter_trigger = starters[3][1]
                st.rerun()
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

# 在此处调用底部句子组件（放在交互拦截及输入框渲染之前，确保它始终在页面加载时渲染）
render_fun_quotes(current_theme['text_color'])

# 优先检测是否由灵感卡片点击触发
triggered_input = st.session_state.get("starter_trigger", None)
if triggered_input:
    user_input = triggered_input
    st.session_state.starter_trigger = None  # 消费完立即重置并移出触发状态
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
                    password=""
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
