# tools/courses_tool.py

import time
import json
import re
import urllib3
import requests
from datetime import datetime, timedelta
from typing import Annotated, List, Dict, Optional
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==========================================================
# 学期参数映射表
# ==========================================================
SEMESTER_MAP = {
    "1": {"xqm": "3", "display": "第一学期", "start_sunday": "2025-09-07"},
    "2": {"xqm": "12", "display": "第二学期", "start_sunday": "2026-03-01"},
    "3": {"xqm": "16", "display": "第三学期", "start_sunday": "2026-07-05"},
}


def map_semester(semester: str) -> tuple:
    """将用户传入的学期参数（1/2/3）转换为教务系统需要的 xqm 代码和显示名称。"""
    if semester not in SEMESTER_MAP:
        for key, value in SEMESTER_MAP.items():
            if value["xqm"] == semester:
                return value["xqm"], value["display"], value["start_sunday"]
        return "3", "第一学期", "2025-09-07"
    info = SEMESTER_MAP[semester]
    return info["xqm"], info["display"], info["start_sunday"]


# ==========================================================
# 节次时间映射
# ==========================================================
JIE_CI_MAP = {
    "1": "08:00-08:45",
    "2": "08:50-09:35",
    "3": "09:50-10:35",
    "4": "10:40-11:25",
    "5": "11:30-12:15",
    "6": "14:05-14:50",
    "7": "14:55-15:40",
    "8": "15:45-16:30",
    "9": "16:40-17:25",
    "10": "17:30-18:15",
    "11": "18:30-19:15",
    "12": "19:20-20:05",
    "13": "20:10-20:55",
}


def parse_jieci(jc_str: str) -> str:
    """
    将节次字符串（如 "1-10节"、"3-5节"、"11-13节"）转换为具体时间范围。
    返回格式如 "08:00-12:15"（多节连上）或 "08:00-08:45, 08:50-09:35"
    """
    if not jc_str:
        return "时间待定"
    
    # 提取节次数字
    match = re.search(r'(\d+)-(\d+)节', jc_str)
    if not match:
        return jc_str
    
    start_jie = int(match.group(1))
    end_jie = int(match.group(2))
    
    if start_jie == end_jie:
        return JIE_CI_MAP.get(str(start_jie), jc_str)
    
    # 多节连上，显示起止时间
    start_time = JIE_CI_MAP.get(str(start_jie), "").split("-")[0]
    end_time = JIE_CI_MAP.get(str(end_jie), "").split("-")[-1]
    
    if start_time and end_time:
        return f"{start_time}-{end_time}"
    
    # 兜底：列出所有节次
    parts = []
    for j in range(start_jie, end_jie + 1):
        parts.append(JIE_CI_MAP.get(str(j), str(j)))
    return "、".join(parts)


def calculate_date(week_str: str, weekday: int, start_sunday: str) -> str:
    """
    根据周次、星期、学期起始周日计算具体日期
    
    Args:
        week_str: "1周"、"2周" 等
        weekday: 1=周一, 7=周日
        start_sunday: 学期第一周周日的日期 "2025-09-07"
    
    Returns:
        "2026-07-09"
    """
    week_num = int(re.search(r'(\d+)', week_str).group(1))
    start_date = datetime.strptime(start_sunday, "%Y-%m-%d")
    # 周次从1开始，weekday从1（周一）到7（周日）
    delta = (week_num - 1) * 7 + (weekday - 1)
    target_date = start_date + timedelta(days=delta)
    return target_date.strftime("%Y-%m-%d")


# ==========================================================
# 核心工具函数
# ==========================================================
@tool(description="通过 API 接口直接查询武汉大学教务系统课程表（无需浏览器），支持指定学年和学期")
def query_whu_schedule(
    state: Annotated[dict, InjectedState],
    year: str = "2025",
    semester: str = "3"
) -> str:
    """
    直接调用武汉大学教务系统课表查询 API，无需启动浏览器。
    通过 LangGraph state 自动获取教务系统 Cookie。

    Args:
        state: LangGraph 状态字典，包含 cookies（内含 educational 字段）
        year: 学年，如 "2025" 表示 2025-2026 学年
        semester: 学期，传入 "1"=第一学期, "2"=第二学期, "3"=第三学期

    Returns:
        str: 格式化后的课程表报告（包含具体日期和上课时间）
    """
    # 1. 映射学期参数
    xqm_code, semester_display, start_sunday = map_semester(semester)

    # 2. 提取 Cookie
    cookie_data = state.get("cookies", {})
    if isinstance(cookie_data, dict):
        cookie_str = cookie_data.get("educational", "")
    else:
        cookie_str = cookie_data

    if not cookie_str:
        return "【系统提示】未检测到教务系统 Cookie（educational），请先调用 login_to_whu_portal 登录。"

    if "JSESSIONID" not in cookie_str:
        return "【系统提示】Cookie 中缺少 JSESSIONID，请重新登录获取有效凭证。"

    # 3. 构造请求
    url = "https://jwgl.whu.edu.cn/kbcx/xskbcx_cxXsgrkb.html?gnmkdm=N2151"

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": cookie_str,
        "Host": "jwgl.whu.edu.cn",
        "Origin": "https://jwgl.whu.edu.cn",
        "Referer": "https://jwgl.whu.edu.cn/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }

    VALIDATE_TOKEN = "fake_captcha_token_for_test:"

    payload = {
        "xnm": year,
        "xqm": xqm_code,
        "kzlx": "ck",
        "xsdm": "",
        "kclbdm": "",
        "kclxdm": "",
        "validate": VALIDATE_TOKEN
    }

    # 4. 发送请求
    proxies = {"http": None, "https": None}
    response = None
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                data=payload,
                headers=headers,
                timeout=15,
                verify=False,
                allow_redirects=False,
                proxies=proxies
            )
            break
        except Exception as e:
            if attempt == 2:
                return f"【网络异常】请求教务系统失败（重试3次）：{str(e)}"
            time.sleep(1)

    if response is None:
        return "【网络异常】未收到任何响应。"

    # 5. 处理响应
    if response.status_code == 401:
        return "【登录失效】教务系统 Cookie 已过期，请重新登录。"
    if response.status_code == 901:
        return "【系统提示】课表查询验证失败，请重新登录获取新凭证。"
    if response.status_code != 200:
        return f"【系统异常】教务系统返回 HTTP {response.status_code}"

    try:
        data = response.json()
    except json.JSONDecodeError:
        return f"【数据异常】教务系统返回非 JSON 格式：{response.text[:200]}"

    kb_list = data.get("kbList", [])
    if not kb_list:
        return f"【系统提示】在 {year}-{int(year)+1} 学年 {semester_display} 未查询到任何课程安排。"

    # 6. 格式化报告（传入学期起始周日用于计算具体日期）
    return format_schedule_report(kb_list, year, semester_display, start_sunday)


# ==========================================================
# 报告格式化函数
# ==========================================================
def format_schedule_report(kb_list: List[Dict], year: str, semester_display: str, start_sunday: str) -> str:
    """将课表数据格式化为可读报告，按课程合并上课时间，包含具体日期和节次时间"""
    
    course_groups: Dict[str, List[Dict]] = {}
    for item in kb_list:
        kcmc = item.get("kcmc", "").strip()
        if not kcmc:
            continue
        if kcmc not in course_groups:
            course_groups[kcmc] = []
        course_groups[kcmc].append(item)
    
    report_lines = []
    report_lines.append(f"📊 【武汉大学课程表查询结果】")
    report_lines.append(f"📅 学年：{year}-{int(year)+1}　　学期：{semester_display}")
    report_lines.append(f"📝 共查询到 {len(course_groups)} 门课程")
    report_lines.append("")
    
    for kcmc, items in sorted(course_groups.items()):
        first = items[0]
        kcxz = first.get("kcxz", "未知性质")
        xf = first.get("xf", "0")
        teacher = first.get("xm", "")
        if not teacher:
            jsxx = first.get("jsxx", "")
            if jsxx and "/" in jsxx:
                teacher = jsxx.split("/")[-1]
        cdmc = first.get("cdmc", "地点待定")
        xqmc = first.get("xqmc", "")
        location = f"{xqmc} {cdmc}" if xqmc else cdmc
        
        # 合并上课时间（包含具体日期和节次时间）
        time_str = merge_course_times_with_details(items, start_sunday)
        
        report_lines.append(f"📚 【{kcmc}】")
        report_lines.append(f"   • 课程性质：{kcxz} | 学分：{xf}")
        report_lines.append(f"   • 教师：{teacher}")
        report_lines.append(f"   • 地点：{location}")
        report_lines.append(f"   • 上课时间：{time_str}")
        report_lines.append("")
    
    return "\n".join(report_lines)


def merge_course_times_with_details(items: List[Dict], start_sunday: str) -> str:
    """
    合并同一课程的所有上课时间，包含具体日期和节次时间。
    
    输入：同一课程的所有 kbList 条目
    输出：类似 "第1周：2026-07-09(周四) 08:00-12:15、2026-07-10(周五) 08:00-12:15"
    """
    # 按周次分组
    week_groups: Dict[str, List[Dict]] = {}
    for item in items:
        zcd = item.get("zcd", "未知周次")
        if zcd not in week_groups:
            week_groups[zcd] = []
        week_groups[zcd].append(item)
    
    week_parts = []
    for zcd, week_items in sorted(week_groups.items()):
        # 按星期排序（xqj 1=周一, 7=周日）
        sorted_items = sorted(week_items, key=lambda x: int(x.get("xqj", 0)))
        
        day_parts = []
        for item in sorted_items:
            xqj = int(item.get("xqj", 1))
            xqjmc = item.get("xqjmc", "未知")
            jc = item.get("jc", "未知节次")
            
            # 计算具体日期
            date_str = calculate_date(zcd, xqj, start_sunday)
            # 获取星期名称
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_name = weekdays[xqj - 1]
            
            # 转换节次为具体时间
            time_range = parse_jieci(jc)
            
            day_parts.append(f"{date_str}({weekday_name}) {time_range}")
        
        week_time_str = "、".join(day_parts)
        
        # 清理周次显示
        zcd_clean = zcd.replace("周", "").strip()
        if zcd_clean.isdigit():
            zcd_display = f"第{zcd_clean}周"
        else:
            zcd_display = zcd
        
        week_parts.append(f"{zcd_display}：{week_time_str}")
    
    return "；".join(week_parts)


# ==========================================================
# 本地测试入口
# ==========================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("【本地测试】课程表 API 工具")
    print("=" * 70)

    # ==================== 请替换为你的真实教务 Cookie ====================
    # 这里填入你的有效 JSESSIONID 和 SF_cookie_1
    # 可以从 login_helper.py 运行后复制输出中的 educational 字段
    TEST_COOKIE = (
        "JSESSIONID=1C2B7C059E3324B6ABCB01BE3859C18D; "
        "SF_cookie_1=87446532"
    )
    # =====================================================================

    test_state = {
        "cookies": {
            "educational": TEST_COOKIE
        }
    }

    print(f"\nCookie 预览: {TEST_COOKIE[:80]}...")
    print("-" * 70)

    # 测试不同学期的课表
    test_cases = [
        ("2025", "3", "第三学期（暑期学校）"),
        ("2025", "2", "第二学期"),
        ("2025", "1", "第一学期"),
    ]

    for year, sem, desc in test_cases:
        print(f"\n查询 {year}-{int(year)+1} 学年 {desc}...")
        try:
            result = query_whu_schedule.invoke({
                "state": test_state,
                "year": year,
                "semester": sem
            })
            print("=" * 70)
            print(f"📊 【结果】{desc}")
            print("=" * 70)
            print(result)
            print("=" * 70)
        except Exception as e:
            print(f"❌ 查询 {desc} 失败: {str(e)}")

    print("\n✅ 测试完成！")