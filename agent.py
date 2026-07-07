# agent.py
import os
from typing import Annotated, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# 导入所有统一打包的工具
from tools import ALL_TOOLS

# 1. 定义全局状态（State），新增 cookie_str 字段
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookie_str: str  # 【新增】用来持久化存储登录成功后的 Cookie 凭证

# 2. 注册工具节点
tool_node = ToolNode(ALL_TOOLS)

# 3. 初始化 DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

llm = ChatOpenAI(
    model="deepseek-chat", 
    openai_api_key=DEEPSEEK_API_KEY,
    openai_api_base="https://api.deepseek.com/v1",
    temperature=0.1
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# 4. 定义大模型思考逻辑
def call_model(state: AgentState):
    messages = state["messages"]
    
    # 检查状态中是否有 Cookie，以便在 Prompt 中动态提醒大模型当前登录状态
    is_logged_in = "已登录" if state.get("cookie_str") else "未登录"
    
    system_prompt = SystemMessage(content=(
        f"你是一个高校校园生活智能助手。当前系统登录状态：【{is_logged_in}】。\n"
        "你能够通过调用工具帮学生查询真实课程表、查询和预约学校图书馆/体育馆、以及查询校园天气。\n"
        "1. 如果系统状态为【未登录】，且用户想要查询课表或预约，你必须【首先调用 login_to_whu_portal 工具】引导用户登录。\n"
        "2. 不要凭空编造任何数据，必须通过调用对应工具获取真实数据。\n"
        "3. 你的回答应当礼貌、简洁。"
    ))
    full_messages = [system_prompt] + list(messages)
    response = llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

# 5. 定义条件路由
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 6. 构建图结构
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ---- 本地运行测试 ----
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=== LuojiaAgent 登录流闭环本地运行测试 ===")
    
    # 初始化状态，此时 cookie_str 为空
    inputs = {"messages": [("user", "帮我查一下明天的课表")]}
    
    # 第一次运行：大模型会发现【未登录】，并自动调用 login_to_whu_portal 弹窗登录
    config = {"configurable": {"thread_id": "test_session_1"}}
    for event in app.stream(inputs, config=config):
        for key, value in event.items():
            print(f"\n-> [当前执行节点: {key}]")
            if "messages" in value:
                last_msg = value["messages"][-1]
                print(f"输出内容: {last_msg.content}")