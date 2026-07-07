# learn/test.py

import os
import sys
# 将项目根目录（LuojiaAgent）动态加入系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Annotated, Sequence, TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition

# 1. 导入课表工具和【新写好的图书馆选座工具】
from tools.courses_tool import query_whu_schedule
from tools.library_tool import query_library_seats

# 整合工具列表：大模型现在有两个“外挂”了！
campus_tools = [query_whu_schedule, query_library_seats]


# ==================== 2. 定义全局状态 (State) ====================
class WHUState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 存放课表 Cookie
    cookie_str: Optional[str]
    # 存放图书馆 Token
    library_token: Optional[str]
    # 存放图书馆 HMAC 签名（由于是动态抓包获取，我们保存在这里）
    library_hmac: Optional[str]


# ==================== 3. 初始化 LLM 并绑定工具 ====================
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="", # 确保填入你的 KEY
    base_url="https://api.deepseek.com/v1"
)
llm_with_tools = llm.bind_tools(campus_tools)


# ==================== 4. 定义节点 (Nodes) ====================

# learn/test.py 中的对应 agent_node 修改

def agent_node(state: WHUState):
    print("\n--- [Agent 节点] 大模型正在思考规划多任务调度... ---")
    
    last_message = state["messages"][-1] if state["messages"] else None
    if last_message and "由于未能成功完成统一身份认证" in last_message.content:
        return {"messages": []}
    
    # 设定系统 Prompt，告知大模型可以传哪些中文图书馆名称
    system_prompt = (
        "你是一个贴心的武汉大学（智慧珞珈）校园生活助手。目前支持查询【课表】和【图书馆座位余量】。\n"
        "【当前日期】：今天是 2026-07-06（星期一）。请根据今天日期为基准计算用户想查询的准确日期。\n"
        "【工具调用指令】：\n"
        "1. 查询课表 (query_whu_schedule)：将 `cookie_str` 传为空字符串 ''。\n"
        "2. 查询图书馆座位 (query_library_seats)：将 `token` 和 `hmac_key` 传为空字符串 ''。\n"
        "   - 大模型只需要提取 `query_date` 和 `library_name` 两个参数。\n"
        "   - `library_name` 只能是：'总馆', '信息分馆', '工学分馆', '医学分馆' 之一。如果用户说“信息学部图书馆”，你传入 `library_name='信息分馆'` 即可。\n"
        "3. 后台代码会自动注入真实的 Cookie、Token 以及复杂的 19位大楼ID 还有签名，你绝不能自己编造或向用户索要这些凭证。"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# 核心安全操作：在工具执行前，自动把保存在 State 里的敏感凭证强行注入进参数中
def secure_tools_node(state: WHUState):
    print("--- [工具节点] 正在安全注入凭证并调用校园服务 API... ---")
    
    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls
    tool_responses = []
    
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        # 场景 A：调用课表
        if tool_name == "query_whu_schedule":
            tool_args["cookie_str"] = state["cookie_str"]
            result_content = query_whu_schedule.invoke(tool_args)
            
        # 场景 B：调用图书馆选座（安全注入 token 和 hmac）
        elif tool_name == "query_library_seats":
            tool_args["token"] = state["library_token"]
            tool_args["hmac_key"] = state["library_hmac"]
            result_content = query_library_seats.invoke(tool_args)
            
        else:
            result_content = f"不支持的工具调用: {tool_name}"
            
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
workflow.add_node("tools", secure_tools_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()


# ==================== 6. 本地运行测试 ====================
if __name__ == "__main__":
    # 模拟抓包获取的有效凭证（有效期内）
    WHU_COOKIE = "PORTAL-TOKEN=..." # 填入你的课表 Cookie
    
    # 填入你抓包到的图书馆真实 Token 和 HMAC 签名
    LIB_TOKEN = "346a90961b37ffa47dfc3da855390d85e276d5b007081214"
    LIB_HMAC = "e8484d1a7a9cd0a684631f226d75f28eaf9efa76773228aa631ff3d31f431235"

    print("启动智慧珞珈多功能 Agent 助手...")
    
    # 这是一个包含“多工具规划”的复杂提问
    question = "帮我看看我明天（7月7号）有没有课？上完课我想去信息分馆自习，帮我看看明天1楼自习室位置多不多？"
    user_message = HumanMessage(content=question)
    
    inputs = {
        "messages": [user_message],
        "cookie_str": WHU_COOKIE,
        "library_token": LIB_TOKEN,
        "library_hmac": LIB_HMAC
    }
    
    final_state = app.invoke(inputs)
    
    print("\n================== 智能体最终回答 ==================")
    print(final_state["messages"][-1].content)