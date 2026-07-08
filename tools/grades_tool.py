# grades_tool.py

import time
from datetime import datetime
from typing import Annotated  # 新增：导入类型注解
from playwright.sync_api import sync_playwright
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState  # 新增：导入 LangGraph 注入状态标记


@tool(description="通过浏览器打开武汉大学教务系统成绩查询页面，用户手动操作查询，程序自动抓取成绩")
def query_whu_grades_realtime(state: Annotated[dict, InjectedState]) -> str:
    """
    仅打开成绩查询页面并自动注入后台已保存的 Cookie，不自动填写任何参数。
    用户需在浏览器中手动选择学年学期、点击【查询】并滑动验证码。
    程序会监听成绩表格的出现，一旦加载完成即自动抓取并关闭浏览器。
    """
    cookies = state.get("cookies", {})
    actual_cookie_str = cookies.get("educational")  # 获取教务系统 Cookie
    # 2. 如果没拿到任何 Cookie，提前拦截，避免后面报错
    if not actual_cookie_str:
        return "【系统提示】未检测到有效的登录 Cookie，请先进行登录。"

    print("\n" + "=" * 50)
    print("【智能体状态：等待用户手动查询成绩】")
    print(" 🚀 启动浏览器，载入登录凭证...")
    print(" 📋 请自行在页面下拉框中选择学年和学期。")
    print(" 👆 点击【查询】按钮，并手动完成滑动验证码。")
    print(" ⏳ 成绩表格出现后程序自动提取（最长等待 120 秒）")
    print("=" * 50 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # 解析并注入 Cookie 凭证
        playwright_cookies = []
        for pair in actual_cookie_str.split("; "):
            if "=" in pair:
                k, v = pair.split("=", 1)
                playwright_cookies.append({"name": k, "value": v, "domain": "jwgl.whu.edu.cn", "path": "/"})
                playwright_cookies.append({"name": k, "value": v, "domain": ".whu.edu.cn", "path": "/"})
        context.add_cookies(playwright_cookies)

        page = context.new_page()
        page.goto("https://jwgl.whu.edu.cn/cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005&layout=default")

        try:
            print("⏳ 等待页面加载...")
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("✅ 页面加载完成，请开始手动操作。")

            # 先检查是否已有成绩（可能是浏览器缓存的页面）
            existing = page.query_selector_all("#tabGrid .jqgrow")
            if existing:
                print("📊 检测到页面已有成绩数据，直接提取...")
                result = parse_grades_from_page(page)
                browser.close()
                return result

            print("⏳ 正在等待您手动查询并加载成绩表格...")

            # 多策略等待数据行出现
            found = False
            for selector in ["#tabGrid .jqgrow", "#tabGrid tbody tr", "#tabGrid tr"]:
                try:
                    page.wait_for_selector(selector, timeout=30000)
                    print(f"✅ 通过选择器 '{selector}' 发现数据行。")
                    found = True
                    break
                except:
                    continue

            if not found:
                print("⏳ 尝试用 JavaScript 检测表格行...")
                try:
                    page.wait_for_function(
                        """
                        () => {
                            const rows = document.querySelectorAll('#tabGrid tbody tr');
                            return rows.length > 0;
                        }
                        """,
                        timeout=30000
                    )
                    print("✅ 通过 JavaScript 检测到数据行。")
                    found = True
                except:
                    pass

            if not found:
                raise Exception("未检测到成绩数据，请确认是否已点击查询并完成验证码。")

            print("🎉 成绩数据已加载，正在提取...")

            result = parse_grades_from_page(page)
            browser.close()
            return result

        except Exception as e:
            browser.close()
            return f"【运行异常】：{type(e).__name__}: {str(e)}"


def parse_grades_from_page(page):
    """
    使用 JavaScript 一次性提取表格中的所有数据。
    返回直接是格式化后的报告字符串。
    """
    data = page.evaluate("""
        () => {
            const rows = document.querySelectorAll('#tabGrid .jqgrow, #tabGrid tbody tr');
            const result = {
                items: [],
                year: '',
                semester: ''
            };
            
            let dataRows = [];
            for (let row of rows) {
                const tds = row.querySelectorAll('td');
                if (tds.length > 10) {
                    dataRows.push(tds);
                }
            }
            
            if (dataRows.length === 0) {
                return result;
            }
            
            for (let tds of dataRows) {
                if (tds.length < 2) continue;
                const year = tds[0] ? tds[0].innerText.trim() : '';
                const semester = tds[1] ? tds[1].innerText.trim() : '';
                if (year && !result.year) {
                    result.year = year;
                }
                if (semester && !result.semester) {
                    result.semester = semester;
                }
                if (result.year && result.semester) break;
            }
            
            if (!result.year) {
                const yearSpan = document.querySelector('#xnxq_chosen .chosen-spanfont');
                if (yearSpan) result.year = yearSpan.innerText.trim();
            }
            if (!result.semester) {
                const semSpan = document.querySelector('#xgxq_chosen .chosen-spanfont');
                if (semSpan) result.semester = semSpan.innerText.trim();
            }
            
            for (let tds of dataRows) {
                if (tds.length < 9) continue;
                const courseName = tds[3] ? tds[3].innerText.trim() : '';
                if (!courseName) continue;
                
                result.items.push({
                    kcmc: courseName,
                    kcxzmc: tds[4] ? tds[4].innerText.trim() : '',
                    xf: tds[5] ? tds[5].innerText.trim() : '0',
                    cj: tds[6] ? tds[6].innerText.trim() : '0',
                    jd: tds[8] ? tds[8].innerText.trim() : '0',
                    jsxm: tds[16] ? tds[16].innerText.trim() : '',
                });
            }
            
            return result;
        }
    """)
    
    items = data.get('items', [])
    year_display = data.get('year', '（未读取到）')
    semester_display = data.get('semester', '（未读取到）')
    
    return format_grade_report(items, year_display, semester_display)


def format_grade_report(items: list, year_display: str, semester_display: str) -> str:
    """生成报告，包含学年学期信息"""
    if not items:
        return f"【系统提示】：未查询到任何成绩记录（学年：{year_display}，学期：{semester_display}），请确认您已正确选择并点击查询。"

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
        f"📅 学年：{year_display}　　学期：{semester_display}",
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