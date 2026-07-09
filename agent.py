# agent.py
import os
import traceback
from langgraph.checkpoint.memory import MemorySaver
from typing import Annotated, Sequence, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from datetime import datetime, timezone, timedelta
def get_system_date_prompt() -> str:
    # 1. 强制获取东八区（北京时间）
    tz_beijing = timezone(timedelta(hours=8))
    now = datetime.now(tz_beijing)
    
    # 2. 计算星期
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    
    # 3. 计算明天（跨月、跨年时，大模型极易算错，我们帮它算好）
    tomorrow = now + timedelta(days=1)
    tomorrow_weekday = weekdays[tomorrow.weekday()]
    
    # 4. 组装成强力约束提示词
    date_prompt = (
        f"⚠️【当前系统物理时间锚点（绝对基准）】\n"
        f"- 今天是：{now.strftime('%Y-%m-%d')} ({weekday})\n"
        f"- 明天是：{tomorrow.strftime('%Y-%m-%d')} ({tomorrow_weekday})\n"
        f"- 当前精准时间刻：{now.strftime('%H:%M:%S')}\n"
        f"当用户使用“明天”、“后天”、“这周五”、“下周”等相对时间时，"
        f"你必须以此时间锚点为基准，在脑中换算出绝对的 YYYY-MM-DD 格式，再将换算后的绝对日期作为参数传给工具。"
        f"绝对不允许使用已经过去的年份或臆造的日期。"
    )
    return date_prompt

# 导入所有统一打包的工具
from tools import ALL_TOOLS
class CampusCookies(TypedDict, total=False):
    zhlj: str
    educational: str
    library_cookie: list  # 👈 这里必须是 list 类型，用于接收 raw_cookies
    library_token: str
    library_jwt_token: str
    library_hmac: str
    library_request_date: str
    library_request_id: str



# 1. 定义全局状态（State），新增 cookie_str 字段
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookies: CampusCookies  # 【新增】用来持久化存储登录成功后的 Cookie 凭证

# 2. 注册工具节点
tool_node = ToolNode(ALL_TOOLS)

# 3. 初始化 DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
llm = ChatOpenAI(
    model="deepseek-chat", 
    openai_api_key="sk-a2f0818b178a45bd9edc4524358c4bbf",
    openai_api_base="https://api.deepseek.com",
    temperature=0.1
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# 4. 定义大模型思考逻辑
def call_model(state: AgentState):
    messages = state["messages"]
    
    # 检查状态中是否有 Cookie，以便在 Prompt 中动态提醒大模型当前登录状态
    is_logged_in = "已登录" if state.get("cookies") else "未登录"
    date_anchor_prompt = get_system_date_prompt()
    
    system_prompt = SystemMessage(content=(
        f"你是一个高校校园生活智能助手。当前系统登录状态：【{is_logged_in}】。\n\n"
        f"当前日期：{date_anchor_prompt}\n\n"
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

memory = MemorySaver()
# 6. 构建图结构
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile(checkpointer=memory)


def run_agent_stream(user_input: str, thread_id: str, student_id: str = "", password: str = ""):
    """
    供前端 Streamlit 循环调用的核心接口。
    输入用户的提问，逐步产出智能体的执行状态、调用了什么工具、以及大模型的最终回答。
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "student_id": student_id,
            "password": password
        }
    }
    inputs = {"messages": [("user", user_input)]}
    
    # 使用同步 updates 模式逐步监听状态机的每一步节点变化
    for chunk in app.stream(inputs, config=config, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if node_name == "tools":
                # 工具节点运行完毕，获取它的返回内容
                if isinstance(node_output, dict):
                    messages = node_output.get("messages", [])
                elif isinstance(node_output, list):
                    messages = node_output
                else:
                    messages = []


                if messages:
                    last_msg = messages[-1]
                    yield {
                        "type": "tool_output",
                        "content": f"📥 工具执行成功，返回结果：\n{last_msg.content}"
                    }
            elif node_name == "agent":
                # 决策节点运行完毕
                messages = node_output.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    # 如果大模型作出了调用工具的决定
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        for tc in last_msg.tool_calls:
                            # 翻译工具名给用户看，提升友好度
                            tool_mapping = {
                                "login_to_whu_portal": "武大统一身份认证",
                                "query_whu_schedule": "教务课表查询",
                                "book_school_facility": "场馆预约系统"
                            }
                            display_name = tool_mapping.get(tc['name'], tc['name'])
                            yield {
                                "type": "tool_start",
                                "content": f"🤖 智能体判定：需要调用【{display_name}】接口..."
                            }
                    else:
                        # 如果大模型没有要调用的工具，说明做出了最终回答
                        yield {
                            "type": "final_answer",
                            "content": last_msg.content
                        }