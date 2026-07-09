# grades_tool.py

import requests
import time
import json
import urllib3
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
    
    Args:
        semester: "1", "2", "3"
    
    Returns:
        (xqm_code, display_name): 如 ("12", "第二学期")
    """
    if semester not in SEMESTER_MAP:
        # 如果传入的是 "12" 或 "3" 等代码，尝试反向查找
        for key, value in SEMESTER_MAP.items():
            if value["xqm"] == semester:
                return value["xqm"], value["display"]
        # 都不匹配，返回默认值
        return "12", "第二学期"
    info = SEMESTER_MAP[semester]
    return info["xqm"], info["display"]


# ==========================================================
# 核心工具函数
# ==========================================================
@tool(description="通过 API 接口直接查询武汉大学教务系统成绩（无需浏览器），支持指定学年和学期")
def query_whu_grades_realtime(
    state: Annotated[dict, InjectedState],
    year: str = "2025",
    semester: str = "2"
) -> str:
    """
    直接调用武汉大学教务系统成绩查询 API，无需启动浏览器。
    通过 LangGraph state 自动获取教务系统 Cookie。

    Args:
        state: LangGraph 状态字典，包含 cookies（内含 educational 字段）
        year: 学年，如 "2025" 表示 2025-2026 学年
        semester: 学期，传入 "1"=第一学期, "2"=第二学期, "3"=第三学期

    Returns:
        str: 格式化后的成绩分析报告
    """
    # -------------------- 1. 映射学期参数 --------------------
    xqm_code, semester_display = map_semester(semester)

    # -------------------- 2. 提取 Cookie（适配 agent.py 的 state） --------------------
    # 与 courses_tool.py 保持一致：从 cookies.educational 取
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
    url = "https://jwgl.whu.edu.cn/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": cookie_str,
        "Host": "jwgl.whu.edu.cn",
        "Origin": "https://jwgl.whu.edu.cn",
        "Referer": "https://jwgl.whu.edu.cn/cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005&layout=default",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    # ==================== 【重要】validate 令牌 ====================
    # 该值从浏览器抓包获取，与 JSESSIONID 绑定。
    # 如果过期，需要从浏览器重新抓取更新。
    # 注意：成绩接口的 validate 与考试接口不同，需要单独抓取
    VALIDATE_TOKEN = "sl4fz4ckumrbtqq6j:"
    # ============================================================

    payload = {
        "xnm": year,
        "xqm": xqm_code,
        "sfzgcj": "",
        "validate": VALIDATE_TOKEN,
        "kcbj": "",
        "pkey": "",
        "_search": "false",
        "nd": str(int(time.time() * 1000)),
        "queryModel.showCount": "15",
        "queryModel.currentPage": "1",
        "queryModel.sortName": "",
        "queryModel.sortOrder": "asc",
        "time": "666"
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
        return f"【系统提示】在 {year}-{int(year)+1} 学年 {semester_display} 未查询到任何成绩记录。"

    # -------------------- 6. 格式化报告 --------------------
    return format_grade_report(items, year, semester_display)


# ==========================================================
# 报告格式化函数
# ==========================================================
def format_grade_report(items: list, year: str, semester_display: str) -> str:
    """将成绩数据格式化为可读报告"""
    total_credits = 0.0
    weighted_gpa_sum = 0.0
    failed_courses = []
    cleaned_lines = []

    for course in items:
        kcmc = course.get("kcmc", "未知课程")
        cj_str = course.get("cj", "0")
        jd_str = course.get("jd", "0.0")
        xf_str = course.get("xf", "0.0")
        kcxzmc = course.get("kcxzmc", "未知性质")
        jsxm = course.get("jsxm", "")

        try:
            cj = float(cj_str) if cj_str else 0.0
        except ValueError:
            cj = 0.0
        try:
            jd = float(jd_str) if jd_str else 0.0
        except ValueError:
            jd = 0.0
        try:
            xf = float(xf_str) if xf_str else 0.0
        except ValueError:
            xf = 0.0

        if xf > 0:
            total_credits += xf
            weighted_gpa_sum += (jd * xf)

        if cj_str and cj_str.replace('.', '', 1).isdigit():
            if cj < 60.0:
                failed_courses.append(f"{kcmc}({cj_str}分)")
        elif "不及格" in cj_str or "不合格" in cj_str:
            failed_courses.append(f"{kcmc}({cj_str})")

        teacher_info = f" | 教师: {jsxm}" if jsxm else ""
        cleaned_lines.append(f"  • 【{kcxzmc}】 {kcmc} | 学分: {xf:.1f} | 成绩: {cj_str} | 绩点: {jd:.2f}{teacher_info}")

    avg_gpa = (weighted_gpa_sum / total_credits) if total_credits > 0 else 0.0
    current_time_str = datetime.now().strftime("%H:%M")

    report_header = [
        f"📊 【武汉大学学生成绩查询结果】",
        f"📅 学年：{year}-{int(year)+1}　　学期：{semester_display}",
        f"⏱️ 数据抓取时间：今天 {current_time_str}",
        f"✅ 该时段总已修学分: {total_credits:.1f} 学分",
        f"🎓 该时段加权平均绩点 (GPA): {avg_gpa:.2f}"
    ]
    if failed_courses:
        report_header.append(f"⚠️ 【学业预警】发现未通过科目: {', '.join(failed_courses)}，请及时安排重修或补考。")
    else:
        report_header.append("🎉 【学业表现】恭喜！未发现任何不及格科目，表现优异，请继续保持！")
    report_header.append("\n明细清单:")

    return "\n".join(report_header + cleaned_lines)


# ==========================================================
# 本地测试入口（与 agent.py 的 state 结构对齐）
# ==========================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("【本地测试】成绩 API 工具（适配 agent.py state）")
    print("=" * 70)

    # ==================== 请替换为你的真实教务 Cookie ====================
    # 成绩接口需要 validate 参数，所以可以保留完整的 Cookie（含 _dx_captcha_vid）
    TEST_COOKIE = (
        "JSESSIONID=xxx; "
        "SF_cookie_1=xxx"
    )
    # =====================================================================

    # 【关键修复】与 agent.py 的 state 结构保持一致
    # agent.py 使用 state["cookies"]，其中 educational 存放教务系统 Cookie
    test_state = {
        "cookies": {
            "educational": TEST_COOKIE
        }
    }

    print(f"\nCookie 预览: {TEST_COOKIE[:80]}...")
    print("-" * 70)

    # 测试第二学期（传入 "2"）
    print("查询 2025-2026 学年第二学期成绩...\n")

    try:
        result = query_whu_grades_realtime.invoke({
            "state": test_state,
            "year": "2025",
            "semester": "2"
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