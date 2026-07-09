# exam_tool.py

import time
import json
import re
import urllib3
import requests
from datetime import datetime
from typing import Annotated
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==========================================================
# 学期参数映射表
# ==========================================================
SEMESTER_MAP = {
    "1": {"xqm": "3", "display": "第一学期"},
    "2": {"xqm": "12", "display": "第二学期"},
    "3": {"xqm": "16", "display": "第三学期"},
}


def map_semester(semester: str) -> tuple:
    """
    将用户传入的学期参数（1/2/3）转换为教务系统需要的 xqm 代码和显示名称。
    """
    if semester not in SEMESTER_MAP:
        for key, value in SEMESTER_MAP.items():
            if value["xqm"] == semester:
                return value["xqm"], value["display"]
        return "3", "第一学期"
    info = SEMESTER_MAP[semester]
    return info["xqm"], info["display"]


# ==========================================================
# 核心工具函数
# ==========================================================
@tool(description="通过 API 接口直接查询武汉大学教务系统期末考试安排（无需浏览器），支持指定学年和学期")
def query_whu_exam_schedule(
    state: Annotated[dict, InjectedState],
    year: str = "2025",
    semester: str = "1"
) -> str:
    """
    直接调用武汉大学教务系统考试安排查询 API，无需启动浏览器。
    通过 LangGraph state 自动获取教务系统 Cookie。

    Args:
        state: LangGraph 状态字典，包含 cookies（内含 educational 字段）
        year: 学年，如 "2025" 表示 2025-2026 学年
        semester: 学期，传入 "1"=第一学期, "2"=第二学期, "3"=第三学期

    Returns:
        str: 格式化后的考试安排报告
    """
    # -------------------- 1. 映射学期参数 --------------------
    xqm_code, semester_display = map_semester(semester)

    # -------------------- 2. 提取 Cookie（适配 agent.py 的 state） --------------------
    # 【修复】与 courses_tool.py 保持一致
    cookie_data = state.get("cookies", {})
    if isinstance(cookie_data, dict):
        cookie_str = cookie_data.get("educational", "")
    else:
        cookie_str = cookie_data

    if not cookie_str:
        return "【系统提示】未检测到教务系统 Cookie（educational），请先调用 login_to_whu_portal 登录。"

    if "JSESSIONID" not in cookie_str:
        return "【系统提示】Cookie 中缺少 JSESSIONID，请重新登录获取有效凭证。"

    # -------------------- 3. 构造请求 --------------------
    url = "https://jwgl.whu.edu.cn/kwgl/kscx_cxXsksxxIndex.html?doType=query&gnmkdm=N358105"

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": cookie_str,
        "Host": "jwgl.whu.edu.cn",
        "Origin": "https://jwgl.whu.edu.cn",
        "Referer": "https://jwgl.whu.edu.cn/kwgl/kscx_cxXsksxxIndex.html?gnmkdm=N358105&layout=default",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    payload = {
        "xnm": year,
        "xqm": xqm_code,
        "ksmcdmb_id": "",
        "kch": "",
        "kc": "",
        "ksrq": "",
        "kkbm_id": "",
        "_search": "false",
        "nd": str(int(time.time() * 1000)),
        "queryModel.showCount": "15",
        "queryModel.currentPage": "1",
        "queryModel.sortName": "",
        "queryModel.sortOrder": "asc",
        "time": "3"
    }

    # -------------------- 4. 发送请求（带重试） --------------------
    response = None
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                data=payload,
                headers=headers,
                timeout=15,
                verify=False,
                allow_redirects=False
            )
            break
        except Exception as e:
            if attempt == 2:
                return f"【网络异常】请求教务系统失败（重试3次）：{str(e)}"
            time.sleep(1)

    if response is None:
        return "【网络异常】未收到任何响应。"

    # -------------------- 5. 处理响应 --------------------
    if response.status_code == 401:
        return "【登录失效】教务系统 Cookie 已过期，请重新登录。"
    if response.status_code != 200:
        return f"【系统异常】教务系统返回 HTTP {response.status_code}"

    try:
        data = response.json()
    except json.JSONDecodeError:
        return f"【数据异常】教务系统返回非 JSON 格式：{response.text[:200]}"

    items = data.get("items", [])
    if not items:
        return f"【系统提示】在 {year}-{int(year)+1} 学年 {semester_display} 未查询到任何考试安排。"

    # -------------------- 6. 格式化报告 --------------------
    return format_exam_report(items, year, semester_display)


# ==========================================================
# 报告格式化函数
# ==========================================================
def format_exam_report(items: list, year: str, semester_display: str) -> str:
    """将考试数据格式化为可读报告"""
    cleaned_lines = []
    
    sorted_items = sorted(items, key=lambda x: x.get("kssj", ""))

    for course in sorted_items:
        kcmc = course.get("kcmc", "未知课程")
        kssj = course.get("kssj", "时间待定")
        cdmc = course.get("cdmc", "地点待定")
        cdxqmc = course.get("cdxqmc", "")
        zwh = course.get("zwh", "")
        jsxx = course.get("jsxx", "")
        xf = course.get("xf", "0")
        ksfs = course.get("ksfs", "")

        teacher = ""
        if jsxx and "/" in jsxx:
            teacher = jsxx.split("/")[-1]
        elif jsxx:
            teacher = jsxx

        location = cdmc
        if cdxqmc and cdxqmc not in location:
            location = f"{cdxqmc} {cdmc}"

        seat_info = f" (座位号: {zwh})" if zwh else ""
        exam_type = f" [{ksfs}]" if ksfs else ""

        cleaned_lines.append(
            f"  • 【{kcmc}】{exam_type} | 学分: {xf} | "
            f"时间: {kssj} | 地点: {location}{seat_info}"
            + (f" | 教师: {teacher}" if teacher else "")
        )

    current_time_str = datetime.now().strftime("%H:%M")

    report_header = [
        f"📊 【武汉大学期末考试安排查询结果】",
        f"📅 学年：{year}-{int(year)+1}　　学期：{semester_display}",
        f"⏱️ 数据抓取时间：今天 {current_time_str}",
        f"📝 共查询到 {len(items)} 门课程的考试安排",
        "\n详细安排如下:"
    ]

    return "\n".join(report_header + cleaned_lines)


# ==========================================================
# 本地测试入口（与 agent.py 的 state 结构对齐）
# ==========================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("【本地测试】考试安排 API 工具（适配 agent.py state）")
    print("=" * 70)

    # ==================== 请替换为你的真实教务 Cookie ====================
    TEST_COOKIE = (
        "JSESSIONID=xxx; "
        "SF_cookie_1=xxx"
    )
    # =====================================================================

    # 【修复】与 courses_tool.py 和 agent.py 保持一致
    test_state = {
        "cookies": {
            "educational": TEST_COOKIE
        }
    }

    print(f"\nCookie 预览: {TEST_COOKIE[:80]}...")
    print("-" * 70)

    print("查询 2025-2026 学年第一学期考试安排...\n")

    try:
        result = query_whu_exam_schedule.invoke({
            "state": test_state,
            "year": "2025",
            "semester": "1"
        })

        print("=" * 70)
        print("📊 【查询结果】")
        print("=" * 70)
        print(result)
        print("\n" + "=" * 70)
        print("✅ 测试完成！")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")