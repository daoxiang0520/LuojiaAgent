# learn/test.py 完整终极对齐版

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Annotated, Sequence, TypedDict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition

from tools.courses_tool import query_whu_schedule
from tools.library_tool import query_library_seats
from tools.login_helper import interactive_whu_login

campus_tools = [query_whu_schedule, query_library_seats]

# ==================== 1. 定义全局状态 (State) ====================
class WHUState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookie_str: Optional[str]        # 课表 Cookie
    library_token: Optional[str]     # 48位自习室会话 Token
    library_jwt_token: Optional[str] # 自习室 JWT 授权 Token
    # 🚀 补齐：保存完整的安全请求头
    library_hmac: Optional[str]
    library_request_date: Optional[str]
    library_request_id: Optional[str]
    raw_cookies: Optional[list]      # 多域名 Session Cookie 列表


# ==================== 2. 初始化 LLM ====================
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="你的_DEEPSEEK_API_KEY", # 确保填入你的 KEY
    base_url="https://api.deepseek.com/v1"
)
llm_with_tools = llm.bind_tools(campus_tools)


# ==================== 3. 定义节点 (Nodes) ====================

def auth_check_node(state: WHUState):
    print("\n--- [鉴权节点] 正在检查登录凭证状态... ---")
    
    # 检测到任意核心凭证缺失，强行一键收割
    if (not state.get("cookie_str") or 
        not state.get("library_token") or 
        not state.get("library_jwt_token") or 
        not state.get("library_hmac") or 
        not state.get("library_request_date") or 
        not state.get("library_request_id") or 
        not state.get("raw_cookies")):
        try:
            credentials = interactive_whu_login()
            # 🚀 修正：将收割到的 7 个参数原封不动地全部返回给状态机，绝不丢弃任何凭证
            return {
                "cookie_str": credentials["cookie_str"],
                "library_token": credentials["library_token"],
                "library_jwt_token": credentials["library_jwt_token"],
                "library_hmac": credentials["library_hmac"],
                "library_request_date": credentials["library_request_date"],
                "library_request_id": credentials["library_request_id"],
                "raw_cookies": credentials["raw_cookies"]
            }
        except Exception as e:
            import traceback
            print("\n❌ 凭证自动收割异常，详细错误如下：")
            traceback.print_exc()
            
            error_msg = AIMessage(content="系统提示：由于登录超时或未成功登录，我暂时无法获取您的校园数据。请重新输入问题重试。")
            return {"messages": [error_msg]}
            
    return state


def agent_node(state: WHUState):
    print("\n--- [Agent 节点] 大模型正在思考规划多任务调度... ---")
    
    last_message = state["messages"][-1] if state["messages"] else None
    if last_message and "由于登录超时或未成功登录" in last_message.content:
        return {"messages": []}
    
    system_prompt = (
        "你是一个贴心的武汉大学（智慧珞珈）校园生活助手。目前支持查询【课表】和【图书馆座位余量】。\n"
        "【当前日期】：今天是 2026-07-06（星期一）。请根据今天日期为基准计算用户想查询的准确日期。\n"
        "【工具调用指令】：\n"
        "1. 查询课表 (query_whu_schedule)：将 `cookie_str` 传为空字符串 ''。\n"
        "2. 查询图书馆座位 (query_library_seats)：将 `raw_cookies` 传为 []，其它 `library_token`、`library_jwt_token`、`library_hmac`、`library_request_date`、`library_request_id` 均传为空字符串 ''。\n"
        "   - 大模型只需要提取 `query_date` 和 `library_name` 两个参数。\n"
        "   - `library_name` 只能是：'总馆', '信息分馆', '工学分馆', '医学分馆' 之一。\n"
        "3. 后台代码会自动从状态中调取注入真实的 Cookie、Token、以及完整复活浏览器的 Session，你绝不能自己编造或向用户索要这些凭证。"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


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
            
        # 场景 B：调用图书馆选座，注入完整的 6 大参数
        elif tool_name == "query_library_seats":
            tool_args["raw_cookies"] = state["raw_cookies"]
            tool_args["library_token"] = state["library_token"]
            tool_args["library_jwt_token"] = state["library_jwt_token"]
            tool_args["library_hmac"] = state["library_hmac"]
            tool_args["library_request_date"] = state["library_request_date"]
            tool_args["library_request_id"] = state["library_request_id"]
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


# ==================== 4. 编排工作流 (Graph) ====================
workflow = StateGraph(WHUState)

workflow.add_node("auth_check", auth_check_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", secure_tools_node)

workflow.add_edge(START, "auth_check")
workflow.add_edge("auth_check", "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()


# ==================== 5. 多轮交互聊天终端 ====================
if __name__ == "__main__":
    print("==================================================")
    print("🏫 欢迎使用“智慧珞珈”多功能 Agent 智能助理！")
    print("==================================================")
    
    # 🚀 修正：在初始状态中，完整初始化这 7 个控制字段
    state = {
        "messages": [],
        "cookie_str": None,
        "library_token": None,
        "library_jwt_token": None,
        "library_hmac": None,
        "library_request_date": None,
        "library_request_id": None,
        "raw_cookies": None
    }
    
    while True:
        try:
            user_input = input("\n珞珈学子说: ")
            if user_input.strip().lower() in ["exit", "quit"]:
                print("谢谢使用，珞珈山再见！")
                break
                
            if not user_input.strip():
                continue
                
            state["messages"].append(HumanMessage(content=user_input))
            state = app.invoke(state)
            
            agent_reply = state["messages"][-1].content
            print(f"\n小助手说: {agent_reply}")
            
        except KeyboardInterrupt:
            print("\n系统强行终止。")
            break
        except Exception as e:
            print(f"\n发生错误: {str(e)}")