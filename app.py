# app.py 完整修复稳定版
import streamlit as st
import uuid
from typing import Generator, Dict
from agent import run_agent_stream

# 页面基础配置必须放在最顶部
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# ===================== 工具函数 =====================
# 原生浏览器朗读函数
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
# 背景配置
if "bg_index" not in st.session_state:
    st.session_state.bg_index = 0
if "bg_opacity" not in st.session_state:
    st.session_state.bg_opacity = 0.65

# 透明度滑块同步回调函数（根治回弹）
def update_opacity():
    st.session_state.bg_opacity = st.session_state.slider_bg_opacity

# 内置多套渐变背景池
bg_list = [
    "linear-gradient(135deg, #e8f0ff 0%, #d6e4ff 100%)",
    "linear-gradient(135deg, #f0f8e8 0%, #e0efd0 100%)",
    "linear-gradient(135deg, #fff0f6 0%, #ffe0ec 100%)",
    "linear-gradient(135deg, #f8f8f8 0%, #e9e9e9 100%)",
    "linear-gradient(135deg, #f0f7ff 0%, #cce0ff 100%)",
]
current_bg = bg_list[st.session_state.bg_index]

# ===================== 侧边栏渲染 =====================
with st.sidebar:
    st.subheader("账号状态")
    if st.session_state.login_fail_msg:
        st.error(st.session_state.login_fail_msg)

    # 登录模块
    if not st.session_state.is_login:
        login_btn = st.button("🔐 点击登录", use_container_width=True, type="primary")
        if login_btn:
            st.session_state.login_fail_msg = ""
            login_generator = run_agent_stream(
                user_input="调用统一身份登录工具完成登录",
                thread_id=st.session_state.thread_id,
                student_id="",
                password=""
            )
            with st.status("正在唤起浏览器登录窗口...", expanded=True) as login_status:
                login_success = False
                try:
                    for event in login_generator:
                        event_type = event.get("type")
                        content = event.get("content", "")
                        login_status.write(content)
                        if event_type == "tool_output":
                            login_success = True
                except Exception as e:
                    st.session_state.login_fail_msg = f"登录异常：{str(e)}"
                    login_status.update(label="❌ 登录失败", state="error", expanded=True)
                    st.rerun()
                if login_success:
                    st.session_state.is_login = True
                    login_status.update(label="✅ 登录完成", state="complete", expanded=False)
                    st.rerun()
                else:
                    st.session_state.login_fail_msg = "未完成浏览器登录验证，请重试"
                    login_status.update(label="❌ 登录失败", state="error", expanded=True)
                    st.rerun()
    else:
        # 仅点击此按钮才会退出登录，输入文字无任何退出逻辑
        logout_btn = st.button("✅ 已登录 | 点击退出登录", use_container_width=True, type="secondary")
        if logout_btn:
            st.session_state.is_login = False
            st.session_state.login_fail_msg = ""
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.messages = []
            # 退出后强制刷新页面，侧边账号状态立刻更新
            st.rerun()

    st.divider()
    st.subheader("🖼️ 背景设置")
    # 无回弹滑块
    st.slider(
        "背景淡化透明度",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
        value=st.session_state.bg_opacity,
        key="slider_bg_opacity",
        on_change=update_opacity,
        help="数值越大背景越浅、越朦胧；数值越小原图色彩越清晰"
    )
    # 切换/重置背景按钮
    col_bg1, col_bg2 = st.columns([1,1])
    with col_bg1:
        if st.button("切换内置背景", use_container_width=True):
            st.session_state.bg_index = (st.session_state.bg_index + 1) % len(bg_list)
            st.rerun()
    with col_bg2:
        if st.button("重置全部背景", use_container_width=True):
            st.session_state.bg_index = 0
            st.session_state.bg_opacity = 0.65
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

# ===================== 全局美化CSS =====================
st.markdown(f"""
<style>
/* 全局全屏统一背景（侧边栏+主栏完全共用） */
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
}}
/* 全局统一柔光遮罩，整页不分栏 */
.stApp::before {{
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background-color: rgba(255, 255, 255, {st.session_state.bg_opacity});
    z-index: -1;
}}
/* 标题居中 */
h1 {{
    text-align: center !important;
}}
div[data-testid="stCaptionContainer"] {{
    text-align: center;
}}
/* 聊天气泡样式 */
.stChatMessage {{
    background: rgba(255,255,255,0.92) !important;
    border-radius: 12px !important;
}}
/* 侧边栏外层完全透明，不遮挡全局背景 */
section[data-testid="stSidebar"] {{
    background: transparent !important;
}}
/* 侧边栏内部容器轻微底板，不割裂背景 */
section[data-testid="stSidebar"] .stVerticalBlock {{
    background: rgba(255,255,255,0.86);
    padding: 12px;
    border-radius: 10px;
}}
/* ===== 美化底部聊天输入框：大圆角+内边距+柔和阴影 ===== */
div[data-testid="stChatInput"] {{
    border-radius: 18px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08) !important;
}}
div[data-testid="stChatInput"] textarea {{
    border-radius: 18px !important;
    padding: 12px 16px !important;
    border: 1px solid #e0e7ff !important;
}}
/* 朗读按钮靠右 */
.stChatMessage div[data-testid="stHorizontalBlock"] {{
    justify-content: flex-end;
}}
</style>
""", unsafe_allow_html=True)

# ========== 主聊天区域 ==========
st.title("🏫 LuojiaAgent 智能校园助手")
st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")
st.divider()
chat_container = st.container(height=600)
with chat_container:
    # 历史对话渲染+朗读按钮
    for msg_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                read_btn = st.button("🔊", key=f"read_msg_{msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(msg["content"])

# 底部圆角美化聊天输入框
user_input = st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)")
if user_input:
    user_input = user_input.strip()
    if user_input == "":
        st.warning("请输入有效提问内容")
        st.stop()
    # 移除所有输入文字判断退出登录的逻辑，只有侧边按钮能退出
    if not st.session_state.is_login:
        st.error("当前未登录，请先点击左侧侧边栏【🔐 点击登录】完成统一身份认证！")
        st.stop()

    # 用户消息存入并渲染
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

    # AI流式回复
    accumulated_answer = ""
    try:
        event_generator: Generator[Dict, None, None] = run_agent_stream(
            user_input=user_input,
            thread_id=st.session_state.thread_id,
            student_id="",
            password=""
        )
        for event in event_generator:
            event_type = event.get("type")
            content = event.get("content", "")
            if event_type == "final_answer":
                accumulated_answer = content
    except Exception as e:
        accumulated_answer = f"系统调用异常：{str(e)}"

    # 输出AI回复气泡
    with chat_container:
        with st.chat_message("assistant"):
            st.markdown(accumulated_answer)
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                new_msg_idx = len(st.session_state.messages)
                read_btn = st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(accumulated_answer)
    # 保存历史对话
    st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})