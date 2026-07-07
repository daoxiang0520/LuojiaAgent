# app.py (前端开发：学生 B 的主要战场)
import streamlit as st
import uuid
# 导入学生 A 写好的核心流式接口
from agent import run_agent_stream

# 设置页面基本信息
st.set_page_config(page_title="LuojiaAgent 校园助手", page_icon="🏫", layout="centered")
st.title("🏫 LuojiaAgent 智能校园助手")
st.caption("基于 DeepSeek 与 LangGraph 构建的武大校园助手系统")

# 1. 侧边栏登录区域
with st.sidebar:
    st.header("🔑 统一身份认证")
    st.markdown("本系统通过 Playwright 模拟浏览器进行 CAS 认证，不会在服务器保存您的密码。")
    student_id = st.text_input("学号", value="202610005")
    password = st.text_input("统一认证密码", type="password", value="your_password")
    
    st.divider()
    st.warning("⚠️ 首次调用接口需要人工验证时，服务器会弹出浏览器窗口，请在弹窗中完成手势/扫码验证。")

# 2. 会话持久化初始化
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# 3. 渲染历史聊天记录
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 4. 监听用户提问
if user_input := st.chat_input("有什么我可以帮您的？(例如：帮我查明天的课表)"):
    # 3.1 立即展示用户输入并存入历史
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    # 3.2 渲染助手的回答
    with st.chat_message("assistant"):
        # 利用 st.status 制作一个非常漂亮的“思考折叠面板”展示执行过程
        status_container = st.status("🧠 正在思考与调用系统接口...", expanded=True)
        final_answer_placeholder = st.empty()
        
        accumulated_answer = ""
        
        # 3.3 循环读取学生 A 的后端接口产出的数据包
        for event in run_agent_stream(
            user_input=user_input,
            thread_id=st.session_state.thread_id,
            student_id=student_id,
            password=password
        ):
            if event["type"] in ["tool_start", "tool_output"]:
                # 把智能体调用工具和返回结果实时打印到 st.status 面板内
                status_container.write(event["content"])
            elif event["type"] == "final_answer":
                # 大模型的最终自然语言总结
                accumulated_answer = event["content"]
                final_answer_placeholder.markdown(accumulated_answer)
                
        # 思考结束，自动折叠状态面板
        status_container.update(label="✅ 接口调度完成", state="complete", expanded=False)
        
        # 保存助手回答到历史记录
        if accumulated_answer:
            st.session_state.messages.append({"role": "assistant", "content": accumulated_answer})