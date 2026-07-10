# agent.py
import os
import traceback
from langgraph.checkpoint.memory import MemorySaver
from typing import Annotated, Sequence, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage
from langchain_deepseek import ChatDeepSeek
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
    cookies: CampusCookies
    pending_input: str | None  # 工具执行期间用户追加的输入，等工具跑完再处理

# 注册工具节点
tool_node = ToolNode(ALL_TOOLS)

# 初始化 DeepSeek — 从 api.key 文件读取密钥
def _load_api_key() -> str:
    key_file = os.path.join(os.path.dirname(__file__), "api.key")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    return os.getenv("DEEPSEEK_API_KEY", "")

llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    api_key=_load_api_key(),
    api_base="https://api.deepseek.com",
    temperature=0.1,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# 定义大模型思考逻辑
def call_model(state: AgentState):
    messages = state["messages"]

    # 检测上一轮未完成（assistant 发了 tool_calls 但工具还没返回）
    # → 用户在一个graph执行里面追加了输入，状态里出现了不完整的消息链
    # → 设置 pending_input 让下次 tool 返回后一起处理
    last = messages[-1] if messages else None
    if hasattr(last, "tool_calls") and last.tool_calls:
        # 找上一个用户消息看看是不是 pending
        return {"messages": []}  # 空返回，等工具执行

    # 拼装追加输入
    extra_msgs = []
    pending = state.get("pending_input")
    if pending:
        from langchain_core.messages import HumanMessage
        extra_msgs.append(HumanMessage(
            content=f"【追加输入】在工具执行期间，用户补充了以下内容：{pending}。请综合考虑此前工具返回的结果和此追加内容，给出最合适的答复。"
        ))

    is_logged_in = "已登录" if state.get("cookies") else "未登录"
    date_anchor_prompt = get_system_date_prompt()
    
    system_prompt = SystemMessage(content=(
    f"你是「珞珈智伴」，一个主动、会思考的武大校园生活管家，不是简单的问答机器人。\n\n"
    f"当前时间：{date_anchor_prompt}\n"
    f"登录状态：{is_logged_in}\n\n"

    "【你是谁】\n"
    "你比学生自己更了解武大——你知道什么时候图书馆有空位、雨天该不该出门、"
    "课表和考试怎么排的。你的价值不是「帮用户查个数据」，而是「替用户想好整件事该怎么办」。\n\n"

    "【你怎么思考】\n"
    "收到用户请求后，不要直奔工具。先在脑中过一遍：\n"
    "1. 用户真正想达成的目标是什么？（不是字面意思，是深层需求）\n"
    "2. 要达成这个目标，我需要了解哪些前提？（课表？天气？座位？）\n"
    "3. 查到的信息之间有没有矛盾？（课表冲突？天气影响出行？）\n"
    "4. 最优方案是什么？有没有备选？\n"
    "5. 有没有用户自己都没想到但你该提醒的事？\n\n"

    "【你怎么行动】\n"
    "- 能一次规划好的事，不要等用户追问再补查。比如用户说「明天想自习」，"
    "你应该主动查课表（确认有空）、查天气（决定带伞）、查座位（找最佳分馆），"
    "然后给出一个完整建议，而不是只返回座位列表等用户继续问。\n"
    "- 发现冲突要主动提醒，不要默默忽略。比如用户预约的时间和课表重叠，"
    "你要说「这个时段有高数课，你确定要预约吗？要不换个时间？」\n"
    "- 有多条路的时候要帮用户比较。比如「总馆有空位但较远，信息分馆满了但工学分馆有座还近，"
    "建议去工学分馆，走过去5分钟，也不下雨。」\n"
    "- 工具返回的结果要翻译成人话。别把原始字段直接甩给用户，要整理成自然的建议。\n"
    "- 用户一个问题里包含多个点时，必须逐条回应，不要遗漏任何一个。\n\n"

    "【注意】\n"
    "- 课程、成绩、考试、座位等信息必须通过工具获取，绝对不要编造。\n"
    "- 关于校园生活的主观问题（哪个食堂好吃、哪个老师怎么样），可以结合自身训练数据回答，"
    "但必须说明这只是参考信息，不是官方数据。\n"
    "- 如果你不确定某个结论是否准确，直接说「这个我不确定，建议你自己确认一下」。\n"
    "- 绝对不允许使用已经过去的年份或臆造的日期。\n\n"

    "【说话方式】\n"
    "- 自然、简洁，像学长学姐帮你参谋，不像客服\n"
    "- 不要用「第一步第二步第三步」这种机械表达\n"
    "- 结论先行，细节补充。比如先说「建议明天下午去工学分馆」，再解释为什么\n"
    "- 3条以上的信息用简短的要点组织，不要大段文字\n"
    ))
    full_messages = [system_prompt] + list(messages) + extra_msgs
    response = llm_with_tools.invoke(full_messages)
    result = {"messages": extra_msgs + [response]}
    if pending:
        result["pending_input"] = None  # 清除，防止下次重复处理
    return result

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

    # 检查上一轮是否未完成（assistant 发了 tool_calls 但工具没跑完）
    last_state = app.get_state(config)
    if last_state and last_state.values:
        last_msgs = last_state.values.get("messages", [])
        if last_msgs:
            last_msg = last_msgs[-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                # 上一轮还在等工具返回 → 不插入新消息，用 pending_input 暂存
                print(f"[agent] 检测到未完成的工具调用，暂存输入: {user_input[:30]}...")
                inputs = {"pending_input": user_input}
                if cookies:
                    inputs["cookies"] = cookies
                for chunk in app.stream(inputs, config=config, stream_mode="updates"):
                    if not isinstance(chunk, dict):
                        continue
                    for node_name, node_output in chunk.items():
                        if node_name == "tools":
                            pass
                        elif node_name == "agent":
                            if isinstance(node_output, dict):
                                msgs = node_output.get("messages", [])
                            else:
                                msgs = node_output if isinstance(node_output, list) else []
                            if msgs:
                                last_m = msgs[-1]
                                if hasattr(last_m, "content") and not (hasattr(last_m, "tool_calls") and last_m.tool_calls):
                                    yield {"type": "tool_output", "content": str(last_m.content)}
                return

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
                if isinstance(node_output, dict):
                    messages = node_output.get("messages", [])
                elif isinstance(node_output, list):
                    messages = node_output
                else:
                    messages = []
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
