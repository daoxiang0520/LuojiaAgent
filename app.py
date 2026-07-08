# app.py 完整版（原生浏览器朗读，无第三方TTS库）
import streamlit as st
import uuid
from typing import Generator, Dict
from agent import run_agent_stream

# 页面基础配置必须放在最顶部
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# 全局CSS：标题居中、对话按钮排版优化
st.markdown("""
<style>
h1 {
    text-align: center !important;
}
div[data-testid="stCaptionContainer"] {
    text-align: center;
}
/* 朗读按钮贴对话右下角 */
.stChatMessage div[data-testid="stHorizontalBlock"] {
    justify-content: flex-end;
}
</style>
""", unsafe_allow_html=True)

# 原生朗读函数（浏览器内置语音，无需pip安装任何包）
def speak_text(text: str):
    # 转义反引号避免JS语法报错
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

# 会话持久化初始化
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
# 登录状态标记
if "is_login" not in st.session_state:
    st.session_state.is_login = False
# 临时登录失败提示缓存
if "login_fail_msg" not in st.session_state:
    st.session_state.login_fail_msg = ""

# ===================== 左侧侧边栏 =====================
with st.sidebar:
    st.subheader("账号状态")
    # 展示登录失败临时提示
    if st.session_state.login_fail_msg:
        st.error(st.session_state.login_fail_msg)

    if not st.session_state.is_login:
        # 未登录状态按钮
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
                        # 只要工具执行完成，直接判定登录成功
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
        # 已登录：退出登录按钮
        logout_btn = st.button("✅ 已登录 | 点击退出登录", use_container_width=True, type="secondary")
        if logout_btn:
            # 清除登录状态
            st.session_state.is_login = False
            st.session_state.login_fail_msg = ""
            # 全新thread_id隔离账号会话
            st.session_state.thread_id = str(uuid.uuid4())
            # 清空当前对话
            st.session_state.messages = []
            st.rerun()

    st.divider()
    st.subheader("💬 快捷操作")
    # 清空当前聊天
    if st.button("🗑️ 清空当前聊天", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.rerun()
    # 新建对话会话
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
    # 历史对话存档
    st.header("📚 历史对话存档")
    st.divider()
    current_tid = st.session_state.thread_id
    session_items = list(st.session_state.all_sessions.items())
    if not session_items:
        st.info("暂无存档\n新建对话后自动保存")
    else:
        for idx, (tid, info) in enumerate(reversed(session_items)):
            title = info["title"]
            msg_count = len(info["messages"])
            if tid == current_tid:
                btn_label = f"🟢 {title} ({msg_count}条)"
                btn_type = "primary"
            else:
                btn_label = f"📄 {title} ({msg_count}条)"
                btn_type = "secondary"
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
    if st.button("🧹 清空所有存档", use_container_width=True, type="secondary"):
        st.session_state.all_sessions = {}
        st.rerun()

# ========== 主聊天区域 ==========
st.title("🏫 LuojiaAgent 智能校园助手")
st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")
st.divider()
chat_container = st.container(height=600)
with chat_container:
    # 渲染历史对话 + 每条对话增加朗读按钮
    for msg_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            # 单行放置朗读按钮
            col_text, col_audio = st.columns([9, 1])
            with col_audio:
                read_btn = st.button("🔊", key=f"read_msg_{msg_idx}", help="朗读本条文本")
                if read_btn:
                    speak_text(msg["content"])

# 聊天输入框固定页面最底部
user_input = st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)")
if user_input:
    if user_input.strip() == "":
        st.warning("请输入有效提问内容")
        st.stop()
    # 未登录拦截
    if not st.session_state.is_login:
        st.error("当前未登录，请先点击左侧侧边栏【🔐 点击登录】完成统一身份认证！")
        st.stop()

    user_input = user_input.strip()
    # 用户消息存入会话并渲染
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
    with chat_container:
        with st.chat_message("assistant"):
            status_container = st.status("🧠 正在思考与调用系统接口...", expanded=True)
            final_placeholder = st.empty()
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
                    if event_type in ["tool_start", "tool_output"]:
                        status_container.write(content)
                    elif event_type == "final_answer":
                        accumulated_answer = content
                        final_placeholder.markdown(accumulated_answer)
            except Exception as e:
                err_msg = f"系统调用异常：{str(e)}"
                status_container.write(f"❌ {err_msg}")
                accumulated_answer = err_msg
                final_placeholder.markdown(accumulated_answer)
            # 更新状态面板
            if accumulated_answer and "异常" not in accumulated_answer:
                status_container.update(label="✅ 接口调度完成", state="complete", expanded=False)
            else:
                status_container.update(label="❌ 执行出错", state="error", expanded=True)
            # 保存AI回复
            if accumulated_answer:
                st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})
                # AI回复下方增加朗读按钮
                col_text, col_audio = st.columns([9, 1])
                with col_audio:
                    new_msg_idx = len(st.session_state.messages) - 1
                    read_btn = st.button("🔊", key=f"read_msg_{new_msg_idx}", help="朗读本条文本")
                    if read_btn:
                        speak_text(accumulated_answer)