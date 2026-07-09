# app.py 新增强制背景过渡动画 + 日间/夜间一键切换模态设置弹窗
import streamlit as st
import uuid
from typing import Generator, Dict

# 页面基础配置必须放在最顶部
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# ===================== 工具函数 =====================
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

# ===================== 会话状态初始化 =====================
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "is_login" not in st.session_state:
    st.session_state.is_login = False
if "login_fail_msg" not in st.session_state:
    st.session_state.login_fail_msg = ""
if "bg_index" not in st.session_state:
    st.session_state.bg_index = 0
if "bg_opacity" not in st.session_state:
    st.session_state.bg_opacity = 0.65
if "auto_read_ai" not in st.session_state:
    st.session_state.auto_read_ai = True
if "show_setting_modal" not in st.session_state:
    st.session_state.show_setting_modal = False
# 昼夜模式标识：day 日间 / night 夜间
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "day"

# 日间渐变背景池
day_bg_list = [
    "linear-gradient(135deg, #e8f0ff 0%, #d6e4ff 100%)",
    "linear-gradient(135deg, #f0f8e8 0%, #e0efd0 100%)",
    "linear-gradient(135deg, #fff0f6 0%, #ffe0ec 100%)",
    "linear-gradient(135deg, #f8f8f8 0%, #e9e9e9 100%)",
    "linear-gradient(135deg, #f0f7ff 0%, #cce0ff 100%)",
]
# 夜间深色渐变背景池
night_bg_list = [
    "linear-gradient(135deg, #19202d 0%, #2c384a 100%)",
    "linear-gradient(135deg, #101828 0%, #1d2939 100%)",
    "linear-gradient(135deg, #202030 0%, #2d2d44 100%)",
    "linear-gradient(135deg, #1a2435 0%, #283850 100%)",
    "linear-gradient(135deg, #23233a 0%, #323250 100%)",
]

# 根据昼夜模式读取对应背景列表
if st.session_state.theme_mode == "day":
    bg_list = day_bg_list
    mask_rgb = "255,255,255"
    text_color = "#111111"
    bubble_bg = "rgba(255,255,255,0.92)"
    sidebar_bg = "rgba(255,255,255,0.86)"
else:
    bg_list = night_bg_list
    mask_rgb = "12,16,24"
    text_color = "#f0f0f0"
    bubble_bg = "rgba(35,40,55,0.88)"
    sidebar_bg = "rgba(28,32,45,0.88)"

current_bg = bg_list[st.session_state.bg_index]

# ===================== 模态设置弹窗 =====================
@st.dialog("系统设置面板", width="small")
def setting_modal():
    st.subheader("🌓 显示模式")
    # 昼夜切换按钮
    col_day, col_night = st.columns(2)
    with col_day:
        if st.button("☀️ 日间模式", use_container_width=True, type="primary" if st.session_state.theme_mode == "day" else "secondary"):
            st.session_state.theme_mode = "day"
            st.rerun()
    with col_night:
        if st.button("🌙 夜间模式", use_container_width=True, type="primary" if st.session_state.theme_mode == "night" else "secondary"):
            st.session_state.theme_mode = "night"
            st.rerun()

    st.divider()
    st.subheader("🖼️ 背景设置")
    # 透明度滑块（实时全局刷新，弹窗不关闭）
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

    # 切换背景（自带强制过渡动画）
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
    # 手动关闭按钮
    if st.button("关闭设置", type="secondary", use_container_width=True):
        st.session_state.show_setting_modal = False
        st.rerun()

# ===================== 顶部标题 + 右上角⚙️设置按钮 =====================
header_row = st.columns([0.92, 0.08])
with header_row[0]:
    st.title("🏫 LuojiaAgent 智能校园助手")
    st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")
with header_row[1]:
    setting_btn = st.button("⚙️ 设置", use_container_width=True, help="打开背景/朗读/显示模式设置面板")
    if setting_btn:
        st.session_state.show_setting_modal = True
        st.rerun()

# 常驻模态弹窗
if st.session_state.show_setting_modal:
    setting_modal()

# ===================== 侧边栏 =====================
with st.sidebar:
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
            btn_col1, btn_col2 = st.columns([4, 1])
            with btn_col1:
                if st.button(btn_label, type=btn_type, use_container_width=True, key=f"switch_{tid}"):
                    st.session_state.thread_id = tid
                    st.session_state.messages = info["messages"].copy()
                    st.rerun()
            with btn_col2:
                if st.button("🗑️", key=f"del_{tid}", help="删除本条存档对话"):
                    del st.session_state.all_sessions[tid]
                    if tid == current_tid:
                        st.session_state.messages = []
                        st.session_state.thread_id = str(uuid.uuid4())
                    st.rerun()
    st.divider()
    if st.button("🧹 清空所有存档", use_container_width=True):
        st.session_state.all_sessions = {}
        st.rerun()

# ===================== 全局CSS（核心：强制背景过渡动画 + 昼夜配色适配） =====================
st.markdown(f"""
<style>
/* 全局背景，强制0.6s平滑过渡动画，无开关永久生效 */
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
    /* 强制切换动画：渐变背景平滑过渡 */
    transition: background-image 0.6s ease-in-out;
}}
/* 遮罩层同步过渡，透明度变化也带动画 */
.stApp::before {{
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background-color: rgba({mask_rgb}, {st.session_state.bg_opacity});
    z-index: -1;
    transition: background-color 0.6s ease-in-out;
}}
/* 全局文字颜色适配昼夜模式 */
.main, .stMarkdown, p, span, label {{
    color: {text_color} !important;
}}
h1 {{
    text-align: center !important;
    color: {text_color} !important;
}}
div[data-testid="stCaptionContainer"] {{
    text-align: center;
    color: {text_color} !important;
}}
/* 聊天气泡自适应昼夜 */
.stChatMessage {{
    background: {bubble_bg} !important;
    border-radius: 12px !important;
}}
/* 侧边栏透明基底自适应昼夜 */
section[data-testid="stSidebar"] {{
    background: transparent !important;
}}
section[data-testid="stSidebar"] .stVerticalBlock {{
    background: {sidebar_bg};
    padding: 12px;
    border-radius: 10px;
}}
/* 聊天输入框圆角美化 */
div[data-testid="stChatInput"] {{
    border-radius: 18px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08) !important;
}}
div[data-testid="stChatInput"] textarea {{
    border-radius: 18px !important;
    padding: 12px 16px !important;
    border: 1px solid #e0e7ff !important;
    background: rgba(255,255,255,0.1);
    color: {text_color} !important;
}}
/* 朗读按钮靠右 */
.stChatMessage div[data-testid="stHorizontalBlock"] {{
    justify-content: flex-end;
}}
/* 右上角⚙️设置按钮样式，防止挤压 */
div[data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton button {{
    margin-top: 18px !important;
    padding: 8px 4px !important;
    font-size: 16px !important;
    min-width: 80px !important;
}}
</style>
""", unsafe_allow_html=True)

# ========== 聊天区域 ==========
chat_container = st.container(height=600)
with chat_container:
    for msg_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                read_btn = st.button("🔊", key=f"read_msg_{msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(msg["content"])

# 聊天输入框
user_input = st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)")
if user_input:
    user_input = user_input.strip()
    if user_input == "":
        st.warning("请输入有效提问内容")
        st.stop()
    if not st.session_state.is_login:
        st.error("当前未登录，请先点击左侧侧边栏【🔐 点击登录】完成统一身份认证！")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                new_msg_idx = len(st.session_state.messages) - 1
                read_btn = st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(user_input)

    accumulated_answer = ""
    with chat_container:
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            try:
                from agent import run_agent_stream
                event_generator: Generator[Dict, None, None] = run_agent_stream(
                    user_input=user_input,
                    thread_id=st.session_state.thread_id,
                    student_id="",
                    password=""
                )
                for event in event_generator:
                    event_type = event.get("type")
                    content = event.get("content", "")
                    if event_type == "stream_chunk":
                        accumulated_answer += content
                        response_placeholder.markdown(accumulated_answer)
                    elif event_type == "final_answer":
                        accumulated_answer = content
                        response_placeholder.markdown(accumulated_answer)
            except Exception as e:
                accumulated_answer = f"系统调用异常：{str(e)}"
                response_placeholder.markdown(accumulated_answer)
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                new_msg_idx = len(st.session_state.messages)
                read_btn = st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(accumulated_answer)
    st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})
    if st.session_state.auto_read_ai and accumulated_answer.strip():
        speak_text(accumulated_answer)