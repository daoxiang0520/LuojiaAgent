# app.py (前端开发：学生 B 的主要战场)
import streamlit as st
import uuid
from typing import Generator, Dict
# 导入学生 A 写好的核心流式接口
from agent import run_agent_stream

# 页面基础配置
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="wide")

# 会话持久化初始化
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# ===================== 全局三栏布局：左认证栏 | 中间聊天主栏 | 右历史存档栏 =====================
col_left, col_main, col_right = st.columns([1, 2.6, 1.1], gap="medium")

# ========== 左侧区域：统一身份认证 + 快捷操作 ==========
with col_left:
    st.header("🔑 统一身份认证")
    st.markdown("本系统通过 Playwright 模拟浏览器进行 CAS 认证，不会在服务器持久保存您的密码。")
    student_id = st.text_input("学号", placeholder="请输入武大学号")
    password = st.text_input("统一认证密码", type="password", placeholder="统一身份认证密码")
    
    st.divider()
    st.warning("⚠️ 首次调用接口需要人工验证时，服务器会弹出浏览器窗口，请在弹窗中完成手势/扫码验证。")
    
    st.divider()
    st.subheader("💬 快捷操作")
    # 清空当前聊天（仅清空当前会话，不存档）
    if st.button("🗑️ 清空当前聊天", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.rerun()
    # 新建对话：自动保存当前对话到右侧存档，生成全新会话
    if st.button("🔄 新建对话会话", use_container_width=True, type="primary"):
        # 当前会话有消息才存入历史存档
        if len(st.session_state.messages) > 0:
            # 提取第一条用户提问作为会话标题
            first_user_msg = next(
                (m["content"] for m in st.session_state.messages if m["role"] == "user"),
                "空白对话"
            )
            session_title = first_user_msg[:20] + "..." if len(first_user_msg) > 20 else first_user_msg
            # 存入全局存档字典
            st.session_state.all_sessions[st.session_state.thread_id] = {
                "title": session_title,
                "messages": st.session_state.messages.copy()
            }
        # 重置全新空白会话
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

# ========== 中间主区域：标题 + 聊天窗口（输入框强制底部） ==========
with col_main:
    st.title("🏫 LuojiaAgent 智能校园助手")
    st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")
    st.divider()

    # 填充空白占位，把输入框压到页面底部
    chat_container = st.container(height=600)
    with chat_container:
        # 渲染当前会话历史聊天记录
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 聊天输入框固定在中间栏最底部
    user_input = st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)")
    if user_input:
        # 前置参数校验
        if not student_id or not password:
            st.error("请先在左侧栏填写学号与统一认证密码！")
            st.stop()
        if user_input.strip() == "":
            st.warning("请输入有效提问内容")
            st.stop()

        user_input = user_input.strip()
        # 存入并渲染用户消息
        st.session_state.messages.append({"role": "user", "content": user_input})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)

        # 助手流式输出区域
        with chat_container:
            with st.chat_message("assistant"):
                status_container = st.status("🧠 正在思考与调用系统接口...", expanded=True)
                final_placeholder = st.empty()
                accumulated_answer = ""
                try:
                    # 流式迭代后端事件
                    event_generator: Generator[Dict, None, None] = run_agent_stream(
                        user_input=user_input,
                        thread_id=st.session_state.thread_id,
                        student_id=student_id,
                        password=password
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
                
                # 更新思考面板状态
                if accumulated_answer and "异常" not in accumulated_answer:
                    status_container.update(label="✅ 接口调度完成", state="complete", expanded=False)
                else:
                    status_container.update(label="❌ 执行出错", state="error", expanded=True)

                # 持久化助手回复到当前会话
                if accumulated_answer:
                    st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})

# ========== 右侧区域：历史对话存档列表 ==========
with col_right:
    st.header("📚 历史对话存档")
    st.divider()
    current_tid = st.session_state.thread_id
    session_items = list(st.session_state.all_sessions.items())

    # 无存档提示
    if not session_items:
        st.info("暂无存档\n新建对话后自动保存")
    else:
        # 倒序展示，最新存档在顶部
        for tid, info in reversed(session_items):
            title = info["title"]
            msg_count = len(info["messages"])
            # 当前活跃会话高亮区分
            if tid == current_tid:
                btn_label = f"🟢 {title} ({msg_count}条)"
                btn_type = "primary"
            else:
                btn_label = f"📄 {title} ({msg_count}条)"
                btn_type = "secondary"
            
            # 一行放置切换按钮 + 删除按钮
            btn_col1, btn_col2 = st.columns([4, 1])
            with btn_col1:
                if st.button(btn_label, type=btn_type, use_container_width=True, key=f"switch_{tid}"):
                    # 切换选中的历史会话
                    st.session_state.thread_id = tid
                    st.session_state.messages = info["messages"].copy()
                    st.rerun()
            with btn_col2:
                if st.button("🗑️", key=f"del_{tid}", help="删除本条存档对话"):
                    del st.session_state.all_sessions[tid]
                    # 如果删除的是当前正在查看的会话，重置空白对话
                    if tid == current_tid:
                        st.session_state.messages = []
                        st.session_state.thread_id = str(uuid.uuid4())
                    st.rerun()
    st.divider()
    # 一键清空全部历史存档
    if st.button("🧹 清空所有存档", use_container_width=True, type="secondary"):
        st.session_state.all_sessions = {}
        st.rerun()