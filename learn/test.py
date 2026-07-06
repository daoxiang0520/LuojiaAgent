# learn/test.py

# ==================== 1. 核心路径补全（关键：防止跨文件夹导入错误） ====================
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

# 导入我们的登录助手和课表工具
from tools.courses_tool import query_whu_schedule
from tools.login_helper import interactive_whu_login

# 汇总工具列表
campus_tools = [query_whu_schedule]


# ==================== 2. 定义全局状态 (State) ====================
class WHUState(TypedDict):
    # 对话历史，用于累积多轮聊天数据
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 全局会话状态：存放我们捕获到的 Cookie
    cookie_str: Optional[str]


# ==================== 3. 初始化 LLM 并绑定工具 ====================
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="API", # 确保填入你的 KEY
    base_url="https://api.deepseek.com/v1"
)
llm_with_tools = llm.bind_tools(campus_tools)


# ==================== 4. 定义节点 (Nodes) ====================

# 节点 1：安全鉴权前置节点 (Auth Check Node)
# learn/test.py 中的 auth_check_node 函数重构

def auth_check_node(state: WHUState):
    """图的第一步：检查并确保有可用的登录 Cookie。"""
    print("\n--- [鉴权节点] 正在检查登录状态... ---")
    
    # 如果没有 Cookie，则唤起浏览器弹窗让用户登录
    if not state.get("cookie_str"):
        try:
            captured_cookie = interactive_whu_login()
            return {"cookie_str": captured_cookie}
        except Exception as e:
            # ==================== 核心修改：打印真实报错堆栈 ====================
            import traceback
            print("\n❌ 调试信息：统一身份认证登录失败，错误堆栈如下：")
            traceback.print_exc()
            print("==================================================\n")
            # ===================================================================
            
            error_msg = AIMessage(content="系统提示：由于未能成功完成统一身份认证登录，我暂时无法为您提供课表查询服务。请重新输入问题重试。")
            return {"messages": [error_msg]}
            
    return state


# 节点 2：决策中心 (Agent Node)
# learn/test.py 中的核心修改部分

# learn/test.py 中的核心修改部分

def agent_node(state: WHUState):
    print("\n--- [Agent 节点] 大模型正在规划课表查询... ---")
    
    last_message = state["messages"][-1] if state["messages"] else None
    if last_message and "由于未能成功完成统一身份认证" in last_message.content:
        return {"messages": []}
    
    # 设定系统 Prompt，实现安全的“参数注入”逻辑
    # 告知模型只需要提取 query_date 一个参数
    system_prompt = (
        "你是一个贴心的武汉大学（智慧珞珈）校园课表助手。\n"
        "【当前日期】：今天是 2026-07-06（星期一）。请根据今天日期为基准计算用户想查询的准确日期。\n"
        "【重要指令】：\n"
        "1. 当调用 query_whu_schedule 工具时，其中的 `cookie_str` 参数你只需传入空字符串 ''，"
        "后台会安全地自动注入真实凭证，你只需要准确提取并传入 `query_date` 即可。\n"
        "比如：用户问“下周二我有什么课”，下周二是 2026-07-14，你调用工具时传入 `query_date='2026-07-14'` 即可，后台工具会自动帮你计算这一周的课程。\n"
        "2. 永远不要自己编造或者向用户索要 `cookie_str`。"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# 节点 3：工具执行节点 (Tools Node)
def secure_tools_node(state: WHUState):
    print("--- [工具节点] 正在安全注入 Cookie 并调用智慧珞珈 API... ---")
    
    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls
    tool_responses = []
    
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name == "query_whu_schedule":
            # 核心安全操作：劫持参数，将保存在全局 State 中的真实 Cookie 注入到调用参数中
            tool_args["cookie_str"] = state["cookie_str"]
            result_content = query_whu_schedule.invoke(tool_args)
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

workflow.add_node("auth_check", auth_check_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", secure_tools_node)

# 设置连线：
# 启动后首先运行 auth_check 进行登录
workflow.add_edge(START, "auth_check")
# 登录完毕后进入 agent 节点做决策
workflow.add_edge("auth_check", "agent")
# 动态判断是调用工具还是结束
workflow.add_conditional_edges("agent", tools_condition)
# 工具执行完后返回 agent
workflow.add_edge("tools", "agent")

app = workflow.compile()


# ==================== 6. 与用户进行多轮对话的交互代码 ====================
if __name__ == "__main__":
    print("==================================================")
    print("🎓 欢迎使用“智慧珞珈”智能助手！")
    print("提示：在对话框输入 'exit' 或 'quit' 即可退出系统。")
    print("==================================================")
    
    # 初始化全局状态变量：我们只维护一个 messages 历史和一个常驻的 cookie_str
    state = {
        "messages": [],
        "cookie_str": None  # 初始为空，第一次查询时会自动拉起浏览器弹窗登录
    }
    
    while True:
        try:
            # 1. 获取用户输入
            user_input = input("\n学子说: ")
            if user_input.strip().lower() in ["exit", "quit"]:
                print("谢谢使用，珞珈山再见！")
                break
                
            if not user_input.strip():
                continue
                
            # 2. 将用户输入封装成 HumanMessage 并注入 state
            state["messages"].append(HumanMessage(content=user_input))
            
            # 3. 运行图
            # 由于 app.invoke 运行完会返回更新后的完整 State
            # 我们直接把返回的 state 覆盖掉旧的 state，这样 Cookie 就会一直保存在内存中！
            state = app.invoke(state)
            
            # 4. 获取大模型最新的一轮回答并输出
            agent_reply = state["messages"][-1].content
            print(f"\n助手答: {agent_reply}")
            
        except KeyboardInterrupt:
            print("\n系统强行终止。")
            break
        except Exception as e:
            print(f"\n发生错误: {str(e)}")