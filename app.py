# app.py
import streamlit as st
import uuid
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
        "theme_mode": "day"
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
# 4. 工具与辅助函数
# ==============================================================================
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
    """动态注入 CSS 样式以支持主题切换和背景动画效果"""
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
    /* 气泡样式自适应 */
    .stChatMessage {{
        background: {current_theme['bubble_bg']} !important;
        border-radius: 12px !important;
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
    /* 侧边栏三点操作按钮微调：精简边框与高度，使其更契合行内布局 */
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
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ==============================================================================
# 5. 模态设置面板 (Dialog)
# ==============================================================================
def reset_setting_modal():
    """当用户通过点击外部、按 ESC 键或右上角 X 键关闭设置弹窗时，清除状态标志"""
    st.session_state.show_setting_modal = False

@st.dialog("系统设置面板", width="small", on_dismiss=reset_setting_modal)
def render_setting_modal():
    st.subheader("🌓 显示模式")
    
    # 优化为单开关模式：开是黑夜，白是优化
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
                
                # 优化重构：历史存档单行化，删除功能收纳在三个点内
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
# 7. 页面头部渲染 (采用 vertical_alignment 完美对齐)
# ==============================================================================
header_row = st.columns([0.88, 0.12], vertical_alignment="bottom")
with header_row[0]:
    st.title("🏫 LuojiaAgent 智能校园助手")
    st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")
with header_row[1]:
    setting_btn = st.button("⚙️ 设置", use_container_width=True, help="打开背景/朗读/显示模式设置面板")
    if setting_btn:
        st.session_state.show_setting_modal = True
        st.rerun()

# 保持设置面板和侧边栏按需运行
if st.session_state.show_setting_modal:
    render_setting_modal()

render_sidebar()

# ==============================================================================
# 8. 主聊天区域与逻辑控制 (Main Interface)
# ==============================================================================
chat_container = st.container(height=600)
with chat_container:
    for msg_idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            col_text, col_audio = st.columns([0.92, 0.08], vertical_alignment="center")
            with col_audio:
                if st.button("🔊", key=f"read_msg_{msg_idx}", help="朗读本条文本", use_container_width=True):
                    speak_text(msg["content"])

# 用户交互处理
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
            # 1. 声明状态容器 (在上方展示思考与工具调用链)
            status_container = st.status("🔍 智能体正在规划与执行...", expanded=True)
            # 2. 声明回答容器 (在下方展示最终回答)
            response_placeholder = st.empty()
            
            try:
                from agent import run_agent_stream
                event_generator: Generator[Dict, None, None] = run_agent_stream(
                    user_input=user_input,
                    thread_id=st.session_state.thread_id,
                    student_id="",
                    password=""
                )
                
                # 将运行过程日志输出到状态容器中
                with status_container:
                    for event in event_generator:
                        event_type = event.get("type")
                        content = event.get("content", "")
                        
                        if event_type == "tool_start":
                            # 渲染智能体思考决策路径
                            st.markdown(f"🧠 **思考决策**\n> {content}")
                        elif event_type == "tool_output":
                            # 渲染工具执行返回结果
                            st.markdown(f"📥 **工具反馈数据**")
                            st.info(content)
                        elif event_type == "final_answer":
                            # 成功捕获最终回答，并更新状态容器为完成状态（默认折叠，用户可展开查看详情）
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
                    
    # 3. 结果保存与语音播报
    st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})
    if st.session_state.auto_read_ai and accumulated_answer.strip():
        speak_text(accumulated_answer)