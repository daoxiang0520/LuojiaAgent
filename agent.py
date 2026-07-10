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
    # 1. 🚀【防守型时区修复】先取绝对标准、无误差的全球统一 UTC 时间，再强制转换为东八区北京时间 [1.2.6]
    # 这能彻底解决 Windows Git Bash、WSL、Docker 容器中常见的“双重时区偏置”导致日期抢跑一天的 Bug！
    now_utc = datetime.now(timezone.utc)
    now_beijing = now_utc.astimezone(timezone(timedelta(hours=8)))
    now = now_beijing.replace(tzinfo=None)  # 抹除 tzinfo 方便进行普通的 naive datetime 运算
    
    # 2. 计算星期
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[now.weekday()]
    
    # 3. 计算明天
    tomorrow = now + timedelta(days=1)
    tomorrow_weekday = weekdays[tomorrow.weekday()]
    
    # 4. 组装成强力约束提示词（升级大模型的服从度，防止其强行脑补日期）
    date_prompt = (
        f"⚠️【当前系统物理时间锚点（绝对唯一基准）】\n"
        f"- 今天是：{now.strftime('%Y-%m-%d')} ({weekday})\n"
        f"- 明天是：{tomorrow.strftime('%Y-%m-%d')} ({tomorrow_weekday})\n"
        f"- 当前精准时间刻：{now.strftime('%H:%M:%S')}\n"
        f"🚨【强制纪律】你必须忘掉你脑中（知识库中）原有的任何日期。当前世界的唯一真实时间必须以此处的“当前系统物理时间锚点”为绝对准则。你回答或计算相对日期时，绝对不允许使用其他任何年份或臆造的日期。"
    )
    return date_prompt

# 导入所有统一打包的工具
from tools import ALL_TOOLS

class CampusCookies(TypedDict, total=False):
    zhlj: str
    castgc: str              # CAS CASTGC 票据 — 免密 SSO 到所有子站的万能钥匙
    educational: str
    library_cookie: list     # 接收 raw_cookies（含 CASTGC，供 Playwright 浏览器注入）
    library_token: str
    library_jwt_token: str
    library_hmac: str
    library_hmac_key: str    # HMAC 签名密钥（从 sessionStorage 提取，可纯 Python 生成签名）
    library_request_date: str
    library_request_id: str

# 定义全局状态（State）
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookies: CampusCookies  # 用来持久化存储登录成功后的 Cookie 凭证

# 注册工具节点
tool_node = ToolNode(ALL_TOOLS)

# 初始化 DeepSeek — 从 api.key 文件读取密钥
def _load_api_key() -> str:
    key_file = os.path.join(os.path.dirname(__file__), "api.key")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    return os.getenv("DEEPSEEK_API_KEY", "")

llm = ChatOpenAI(
    model="deepseek-chat",
    openai_api_key=_load_api_key(),
    openai_api_base="https://api.deepseek.com",
    temperature=0.1
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# 定义大模型思考逻辑
def call_model(state: AgentState):
    messages = state["messages"]
    
    is_logged_in = "已登录" if state.get("cookies") else "未登录"
    date_anchor_prompt = get_system_date_prompt()
    
    system_prompt = SystemMessage(content=(
    f"你是一个武大校园生活助手。当前登录状态：【{is_logged_in}】。\n\n"
    f"当前日期：{date_anchor_prompt}\n\n"
    "绝对不允许使用已经过去的年份或臆造的日期。\n"
    
    "【核心规则】\n"
    "用户提到出门/自习/图书馆/体育馆时，必须先查课表,确定要出行再查天气,最后执行请求。\n"
    "• 有课 → 提醒用户（课程名、时间、地点），询问是否确认出门\n"
    "• 没课 → 正常推进\n"
    "• 用户说「逃课/不用查课表」时跳过课表检查\n\n"
    
    "【输出要求】\n"
    "用流畅自然的对话方式回应，并且简洁明了，不要用「第一步/第二步」等机械步骤描述。\n"
    "对于不清楚，未经准确查证的关于课程、考试、座位等等相关的信息不得编造（例如：不要未查证就告诉用户这是最后一节课。）\n"
    "对于关于校园生活的其他问题，无对应调用工具时可以结合自身训练数据训练搜索，但必须提示这是结合自身训练数据得出的，不一定准确（例如：武大哪个食堂好吃）\n"
    ))
    full_messages = [system_prompt] + list(messages)
    response = llm_with_tools.invoke(full_messages)
    return {"messages": [response]}

# 定义条件路由
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

memory = MemorySaver()
# 构建图结构
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile(checkpointer=memory)

def get_agent_cookies(thread_id: str) -> dict:
    """
    从 LangGraph Checkpointer 中获取指定 thread_id 的 cookies 状态，
    供 Streamlit 调用并持久化存储。
    """
    config = {"configurable": {"thread_id": thread_id}}
    state = app.get_state(config)
    if state and state.values:
        return state.values.get("cookies")
    return None

def run_agent_stream(user_input: str, thread_id: str, student_id: str = "", password: str = "", cookies: dict = None):
    """
    供前端 Streamlit 循环调用的核心接口。
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "student_id": student_id,
            "password": password
        }
    }
    inputs = {"messages": [("user", user_input)]}
    
    # 每次运行前，若前端传来了持久化 cookies 凭证，则注入到新会话状态中
    if cookies:
        inputs["cookies"] = cookies
    
    # 使用同步 updates 模式逐步监听状态机的每一步节点变化
    for chunk in app.stream(inputs, config=config, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if node_name == "tools":
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
                messages = node_output.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        for tc in last_msg.tool_calls:
                            tool_mapping = {
                                "login_to_whu_portal": "武大统一身份认证",
                                "query_whu_schedule": "教务课表查询",
                                "query_library_seats": "图书馆座位大盘",
                                "query_empty_seats_in_area": "区域座位分布图",
                                "reserve_library_seat": "图书馆座位预约",
                                "query_user_reservations": "预约记录查询",
                                "cancel_library_reservation": "取消预约",
                                "get_current_usage": "当前使用中座位",
                                "stop_library_usage": "结束使用(签退)",
                                "query_whu_grades_realtime": "成绩查询",
                                "query_whu_exam_schedule": "考试安排查询",
                                "get_whu_rain_forecast": "校园天气预测",
                            }
                            display_name = tool_mapping.get(tc['name'], tc['name'])
                            yield {
                                "type": "tool_start",
                                "content": f"🤖 智能体判定：需要调用【{display_name}】接口..."
                            }
                    else:
                        yield {
                            "type": "tool_output",
                            "content": last_msg.content
                        }
