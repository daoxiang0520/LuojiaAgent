import os
from typing import Annotated, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# 导入组员统一打包的工具列表
from tools import ALL_TOOLS

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# 注册工具节点
tool_node = ToolNode(ALL_TOOLS)

# 1. 从环境变量读取 DeepSeek Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your_default_key_here")  # 请确保在运行前设置环境变量 DEEPSEEK_API_KEY

# 2. 正确初始化 DeepSeek
llm = ChatOpenAI(
    model="deepseek-chat", 
    openai_api_key=DEEPSEEK_API_KEY,
    openai_api_base="https://api.deepseek.com/v1",
    temperature=0.1
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# 3. 定义大模型思考逻辑
def call_model(state: AgentState):
    messages = state["messages"]
    system_prompt = SystemMessage(content=(
        "你是一个高校校园生活智能助手。你能够通过调用工具来帮学生查询真实的课程表、查询和预约学校图书馆/体育馆、以及查询校园天气。\n"
        "1. 如果用户查询信息不完整（例如：未提供查询日期），你必须主动追问用户补充，不要瞎猜。\n"
        "2. 不要凭空编造结果，必须通过调用工具获取真实数据。\n"
        "3. 你的回答应当礼貌、简洁。"
    ))
    full_messages = [system_prompt] + list(messages)
    response = llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

# 4. 定义条件路由
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 5. 构建图结构
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ---- 本地运行测试 ----
if __name__ == "__main__":
    print("=== LuojiaAgent 本地运行测试 ===")
    mock_config = {
        "configurable": {
            "thread_id": "test_session_1",
            "student_id": "202610005",  # 模拟学号
            "password": "your_password"   # 模拟密码
        }
    }
    user_query = "帮我查一下明天的课表"
    print(f"\n用户提问: {user_query}")
    
    inputs = {"messages": [("user", user_query)]}
    for event in app.stream(inputs, config=mock_config):
        for key, value in event.items():
            print(f"\n-> [当前执行节点: {key}]")
            if "messages" in value:
                last_msg = value["messages"][-1]
                print(f"输出内容: {last_msg.content}")
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"调用的工具: {last_msg.tool_calls}")