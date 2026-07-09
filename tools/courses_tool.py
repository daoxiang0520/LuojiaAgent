# tools/courses_tool.py

import time
import json
import re
import urllib3
import requests
from datetime import datetime
from typing import Annotated, List, Dict, Any
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
        # 如果传入的是 "12" 或 "3" 等代码，尝试反向查找
        for key, value in SEMESTER_MAP.items():
            if value["xqm"] == semester:
                return value["xqm"], value["display"]
        return "3", "第一学期"
    info = SEMESTER_MAP[semester]
    return info["xqm"], info["display"]


def extract_captcha_vid(cookie_str: str) -> str:
    """
    从 Cookie 字符串中提取 _dx_captcha_vid 的值
    """
    match = re.search(r'_dx_captcha_vid=([^;]+)', cookie_str)
    if match:
        return match.group(1).strip()
    return ""


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
        str: 格式化后的课程表报告
    """
    # -------------------- 1. 映射学期参数 --------------------
    xqm_code, semester_display = map_semester(semester)

    # -------------------- 2. 提取 Cookie（适配 agent.py 的 state） --------------------
    cookie_data = state.get("cookies", {})
    if isinstance(cookie_data, dict):
        cookie_str = cookie_data.get("educational", "")
    else:
        cookie_str = cookie_data

    if not cookie_str:
        return "【系统提示】未检测到教务系统 Cookie（educational），请先调用 login_to_whu_portal 登录。"

    if "JSESSIONID" not in cookie_str:
        return "【系统提示】Cookie 中缺少 JSESSIONID，请重新登录获取有效凭证。"

    # 提取 _dx_captcha_vid 构造 validate 参数
    captcha_vid = extract_captcha_vid(cookie_str)
    validate_value = f"{captcha_vid}:" if captcha_vid else ""

    # -------------------- 3. 构造请求 --------------------
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

    payload = {
        "xnm": year,
        "xqm": xqm_code,
        "kzlx": "ck",
        "xsdm": "",
        "kclbdm": "",
        "kclxdm": "",
        "validate": validate_value
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

    kb_list = data.get("kbList", [])
    if not kb_list:
        return f"【系统提示】在 {year}-{int(year)+1} 学年 {semester_display} 未查询到任何课程安排。"

    # -------------------- 6. 格式化报告 --------------------
    return format_schedule_report(kb_list, year, semester_display)


# ==========================================================
# 课表数据解析与格式化
# ==========================================================
def format_schedule_report(kb_list: List[Dict], year: str, semester_display: str) -> str:
    """将课表数据格式化为可读报告，按课程合并上课时间"""

    # 按课程名称分组
    course_groups: Dict[str, List[Dict]] = {}
    for item in kb_list:
        kcmc = item.get("kcmc", "").strip()
        if not kcmc:
            continue
        if kcmc not in course_groups:
            course_groups[kcmc] = []
        course_groups[kcmc].append(item)

    # 构建报告
    report_lines = []
    report_lines.append(f"📊 【武汉大学课程表查询结果】")
    report_lines.append(f"📅 学年：{year}-{int(year)+1}　　学期：{semester_display}")
    report_lines.append(f"📝 共查询到 {len(course_groups)} 门课程")
    report_lines.append("")

    # 按课程名排序
    for kcmc, items in sorted(course_groups.items()):
        # 提取基本信息（取第一条）
        first = items[0]
        kcxz = first.get("kcxz", "未知性质")
        xf = first.get("xf", "0")

        # 提取教师姓名（优先用 xm）
        teacher = first.get("xm", "")
        if not teacher:
            jsxx = first.get("jsxx", "")
            if jsxx and "/" in jsxx:
                teacher = jsxx.split("/")[-1]
            else:
                teacher = jsxx

        # 提取地点
        cdmc = first.get("cdmc", "地点待定")
        xqmc = first.get("xqmc", "")
        location = f"{xqmc} {cdmc}" if xqmc else cdmc

        # 合并上课时间
        time_str = merge_course_times(items)

        report_lines.append(f"📚 【{kcmc}】")
        report_lines.append(f"   • 课程性质：{kcxz} | 学分：{xf}")
        report_lines.append(f"   • 教师：{teacher}")
        report_lines.append(f"   • 地点：{location}")
        report_lines.append(f"   • 上课时间：{time_str}")
        report_lines.append("")

    return "\n".join(report_lines)


def merge_course_times(items: List[Dict]) -> str:
    """
    合并同一课程的所有上课时间，生成符合用户要求的格式。

    输入：同一课程的所有 kbList 条目
    输出：类似 "第1周：周一 第1-10节、周二 第1-10节；第2周：周三 第3-5节"
    """
    # 按周次分组
    week_groups: Dict[str, List[Dict]] = {}
    for item in items:
        zcd = item.get("zcd", "未知周次")
        if zcd not in week_groups:
            week_groups[zcd] = []
        week_groups[zcd].append(item)

    # 对每个周次，提取星期和节次信息
    week_parts = []
    for zcd, week_items in sorted(week_groups.items()):
        # 按星期排序（xqj 1=周一, 7=周日）
        sorted_items = sorted(week_items, key=lambda x: int(x.get("xqj", 0)))

        day_parts = []
        for item in sorted_items:
            xqjmc = item.get("xqjmc", "未知")
            jc = item.get("jc", "未知节次")
            day_parts.append(f"{xqjmc} {jc}")

        # 同一周内多个时间用顿号连接
        week_time_str = "、".join(day_parts)

        # 清理周次显示（"1周" -> "第1周"）
        zcd_clean = zcd.replace("周", "").strip()
        if zcd_clean.isdigit():
            zcd_display = f"第{zcd_clean}周"
        else:
            zcd_display = zcd

        week_parts.append(f"{zcd_display}：{week_time_str}")

    # 不同周次用分号连接
    return "；".join(week_parts)


# ==========================================================
# 本地测试入口（与 agent.py 的 state 结构对齐）
# ==========================================================
if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 70)
    print("【本地测试】课程表 API 工具（适配 agent.py state）")
    print("=" * 70)

    # ==================== 请替换为你的真实教务 Cookie ====================
    TEST_COOKIE = (
        "_dx_uzZo5y=1772412944988EPSbTOS2Y6N9e7OiD3wIuZvCAcdG4ntE; "
        "JSESSIONID=F5F5A2668451E05B1C02437547CFA7B6; "
        "SF_cookie_1=87446532;"
        "_dx_captcha_vid=sljhlbk8mrcv048y"
    )
    # =====================================================================

    # 模拟 agent.py 中的 state 结构
    test_state = {
        "cookies": {
            "educational": TEST_COOKIE
        }
    }

    print(f"\nCookie 预览: {TEST_COOKIE[:80]}...")
    print("-" * 70)

    # ---------- 调试：直接发送请求并打印 JSON 前300字符 ----------
    print("\n【调试】直接发送请求，打印原始 JSON 前300字符...")
    print("-" * 70)

    captcha_vid = extract_captcha_vid(TEST_COOKIE)
    validate_val = f"{captcha_vid}:" if captcha_vid else ""

    debug_url = "https://jwgl.whu.edu.cn/kbcx/xskbcx_cxXsgrkb.html?gnmkdm=N2151"
    debug_headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Cookie": TEST_COOKIE,
        "Host": "jwgl.whu.edu.cn",
        "Origin": "https://jwgl.whu.edu.cn",
        "Referer": "https://jwgl.whu.edu.cn/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }
    debug_payload = {
        "xnm": "2025",
        "xqm": "16",
        "kzlx": "ck",
        "xsdm": "",
        "kclbdm": "",
        "kclxdm": "",
        "validate": validate_val
    }

    try:
        debug_resp = requests.post(debug_url, data=debug_payload, headers=debug_headers, timeout=15, verify=False)
        print(f"调试状态码: {debug_resp.status_code}")
        if debug_resp.status_code == 200:
            raw_json = debug_resp.text
            print(f"原始 JSON 前300字符:\n{raw_json[:300]}...")
            # 尝试解析并打印 kbList 数量
            try:
                debug_data = debug_resp.json()
                kb_count = len(debug_data.get("kbList", []))
                print(f"kbList 条目数: {kb_count}")
            except:
                pass
        else:
            print(f"调试请求失败，状态码: {debug_resp.status_code}")
            print("响应预览:", debug_resp.text[:200])
    except Exception as e:
        print(f"调试请求异常: {e}")
    print("-" * 70)

    # ---------- 正式调用工具 ----------
    print("\n查询 2025-2026 学年第三学期（暑期学校）课程表...\n")

    try:
        result = query_whu_schedule.invoke({
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