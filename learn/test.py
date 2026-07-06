# learn/test.py

# ==================== 1. 核心路径补全（防止跨文件夹导入错误） ====================
import os
import sys
# 将项目根目录（LuojiaAgent）动态加入系统路径，确保能顺利导入 tools 文件夹
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Annotated, Sequence, TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition

# 仅从 tools 包中导入编写好的课表工具
from tools.courses_tool import query_whu_schedule

# 整合工具列表
campus_tools = [query_whu_schedule]


# ==================== 2. 定义全局状态 (State) ====================
class WHUState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookie_str: Optional[str]


# ==================== 3. 初始化 LLM 并绑定工具 ====================
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="sk-a2f0818b178a45bd9edc4524358c4bbf", # 确保填入你的 KEY
    base_url="https://api.deepseek.com"
)
llm_with_tools = llm.bind_tools(campus_tools)


# ==================== 4. 定义节点 (Nodes) ====================

def agent_node(state: WHUState):
    print("\n--- [Agent 节点] 大模型正在思考规划课表查询... ---")
    
    # 设定系统 Prompt，实现安全的“参数注入”逻辑
    # 明确告诉模型不需要操心 cookie_str 参数，只需要提取起止日期
    system_prompt = (
        "你是一个贴心的武汉大学（智慧珞珈）校园课表助手。\n"
        "【当前日期】：今天是 2026-07-06（星期一）。请根据今天日期为基准计算用户想查询的准确日期区间。\n"
        "【重要指令】：\n"
        "1. 当调用 query_whu_schedule 工具时，其中的 `cookie_str` 参数你只需传入空字符串 ''，"
        "后台会安全地自动注入真实凭证，你只需要准确提取并传入 `begin_date` 和 `end_date` 即可。\n"
        "2. 永远不要自己编造或者向用户索要 `cookie_str`。"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# 核心逻辑：工具执行与安全凭证拦截注入
def secure_tools_node(state: WHUState):
    print("--- [工具节点] 正在安全注入 Cookie 并调用智慧珞珈 API... ---")
    
    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls
    tool_responses = []
    
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        # 仅处理 query_whu_schedule，拦截并替换 cookie_str
        if tool_name == "query_whu_schedule":
            # 劫持参数，将保存在全局 State 中的真实 Cookie 注入到调用参数中
            tool_args["cookie_str"] = state["cookie_str"]
            result_content = query_whu_schedule.invoke(tool_args)
        else:
            result_content = f"不支持的工具调用: {tool_name}"
            
        # 封装为 ToolMessage 返回给状态机
        tool_msg = ToolMessage(
            content=result_content, 
            tool_call_id=tool_call["id"],
            name=tool_name
        )
        tool_responses.append(tool_msg)
        
    return {"messages": tool_responses}


# ==================== 5. 编排工作流 (Graph) ====================
workflow = StateGraph(WHUState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", secure_tools_node) # 注册为 "tools" 节点以适配 tools_condition

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()


# ==================== 6. 本地运行测试 ====================
if __name__ == "__main__":
    # 模拟有效的智慧珞珈 Cookie（有效期内）
    WHU_COOKIE = (
        "PORTAL-TOKEN=eyJhbGciOiJIUzUxMiJ9.eyJQT1JUQUwtTE9HSU4tVVNFUi1LRVk6IjoiUE9SVEFMX1VTRVJfS0VZOjEwMjQtMjAyNTMwMjExNDIyMS1YeHl3QkxrVl8ifQ.MpiVyBFZAXrpnhc5h7xmpGlpYaoa77APin99Ndl2FSLSAbxZv0rkwAGnpLLwStZSpv3v4q1YqqrtUxXIbJATRw; "
        "zhlj_authorization=c6PXO7xy6ImDNqKMHgTEa2NlcxKeS5owlM0PLC0eyCaC7sCDVYV27ZazToBj5p210Ube5W4TJCVAj8kwz1xt7PBUXbh13pjEiZ6PSicccXp6J1ArmkB5geyDdXk7QUWe; "
        "JSESSIONID=92E83E2B5C9375F0350A6693CA513392; "
        "route=d74fef88aa66f667f8a30f0c9e5f5fc9"
    )

    print("启动智慧珞珈 Agent 课表服务...")
    
    # 精准提问：下周一（2026-07-13）至下周二（2026-07-14）
    question = "帮我看看下周一到下周二我有什么课？"
    user_message = HumanMessage(content=question)
    
    inputs = {
        "messages": [user_message],
        "cookie_str": WHU_COOKIE
    }
    
    final_state = app.invoke(inputs)
    
    print("\n================== 智能体最终回答 ==================")
    print(final_state["messages"][-1].content)