import requests
import time
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool


def format_forecast_time(iso_time_str: str, now_beijing: datetime) -> str:
    """
    将 API 返回的 ISO 时间（如 "2026-07-07T15:00"）转换为中文友好描述。
    依赖外部传入的 now_beijing 来准确判断是“今天”还是“明天”。
    """
    try:
        dt = datetime.fromisoformat(iso_time_str)
    except:
        return iso_time_str  # 解析失败则原样返回

    # 判断日期
    if dt.date() > now_beijing.date():
        day_prefix = "明天"
    else:
        day_prefix = "今天"

    # 转换为 12 小时制
    hour = dt.hour
    if hour == 0:
        ampm_str = "凌晨 12:00 (AM)"
    elif hour < 12:
        ampm_str = f"上午 {hour:02d}:00 (AM)"
    elif hour == 12:
        ampm_str = "中午 12:00 (PM)"
    else:
        ampm_str = f"下午 {hour - 12:02d}:00 (PM)"

    return f"{day_prefix}{ampm_str}"


@tool
def get_whu_rain_forecast() -> str:
    """
    武汉大学（珞珈山）精准降雨及温度预测工具。
    包含未来3小时即时风险、未来12小时持续时间、及穿衣防晒建议。
    """
    lat, lon = 30.5378, 114.3567

    # --- 1. 请求 Open-Meteo 天气接口 ---
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=precipitation_probability,precipitation,temperature_2m"
        f"&timezone=Asia/Shanghai"
    )

    # --- 局部重试机制（防网络抖动） ---
    max_attempts = 3
    response = None
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException as e:
            if attempt == max_attempts - 1:
                return f"工具异常：天气接口连接失败，原因: {str(e)}"
            time.sleep(1)

    if not response or response.status_code != 200:
        return f"工具异常：天气服务器返回状态码 {response.status_code if response else 'None'}"

    # --- 2. 解析 JSON 数据 ---
    data = response.json()
    hourly_data = data.get("hourly", {})
    times = hourly_data.get("time", [])
    probabilities = hourly_data.get("precipitation_probability", [])
    precipitations = hourly_data.get("precipitation", [])
    temperatures = hourly_data.get("temperature_2m", [])

    if not times:
        return "工具异常：气象接口返回的数据结构不完整。"

    # ==================== 【修复点 1：强制使用东八区时间】 ====================
    now_beijing = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
    current_hour_str = now_beijing.strftime("%Y-%m-%dT%H:00")

    # 在 API 返回的时间列表中，精确对齐到当前小时
    current_index = 0
    try:
        current_index = times.index(current_hour_str)
    except ValueError:
        # 兜底：寻找时间差最小的那个索引
        min_diff = float('inf')
        for idx, t_str in enumerate(times):
            t_dt = datetime.fromisoformat(t_str)
            diff = abs((t_dt - now_beijing).total_seconds())
            if diff < min_diff:
                min_diff = diff
                current_index = idx

    print(f"--- [对齐日志] 东八区时间: {now_beijing.strftime('%Y-%m-%d %H:%M')}, "
          f"对齐索引: {current_index} ({times[current_index]}) ---")

    # ==================== 【修复点 2：未来 3 小时从下个整点开始】 ====================
    next_3_hours_rain = False
    max_prob_3_hours = 0
    # 循环 range(1, 4)：跳过当前不完整小时，取未来 3 个完整小时
    for i in range(1, 4):
        target_idx = current_index + i
        if target_idx < len(probabilities):
            prob = probabilities[target_idx]
            max_prob_3_hours = max(max_prob_3_hours, prob)
            if prob >= 30 or precipitations[target_idx] > 0.1:
                next_3_hours_rain = True

    # ==================== 【修复点 3：12小时降雨也同步修正起点】 ====================
    rain_duration = 0
    rain_start_index = -1
    # 循环 range(1, 13)：从下个小时开始，取未来 12 个完整小时
    for i in range(1, 13):
        target_idx = current_index + i
        if target_idx < len(probabilities):
            if probabilities[target_idx] >= 30:
                rain_duration += 1
                if rain_start_index == -1:
                    rain_start_index = target_idx

    # ==================== 【处理温度数据（未来 12 小时）】 ====================
    # 当前温度使用 current_index（当前整点实测值，离现在最近的真实数据）
    current_temp = temperatures[current_index] if temperatures else 25.0

    # 未来温度从下一个小时开始取（与降雨预测起点一致）
    end_idx = min(current_index + 13, len(temperatures))
    temp_12h = temperatures[current_index + 1 : end_idx] if temperatures else [25.0, 25.0]
    if not temp_12h:
        temp_12h = [25.0, 25.0]

    min_temp = min(temp_12h)
    max_temp = max(temp_12h)
    temp_diff = max_temp - min_temp

    # ==================== 【构造人性化报告】 ====================
    current_time_str = now_beijing.strftime("%H:%M")
    analysis = f"【武汉大学（珞珈山）专属气象分析（更新于 {current_time_str}）】\n\n"

    # --- 3小时降水提醒 ---
    if next_3_hours_rain:
        analysis += (
            f"⚠️ 降水提醒：**未来 3 个完整小时内（从下个整点起）有明显的降雨风险！** "
            f"最大下雨概率达 {max_prob_3_hours}%。\n"
            f"💡 **请千万记得带伞！** 如果有户外出行计划，建议暂缓或调整为室内活动。\n\n"
        )
    else:
        analysis += f"✅ 降水提醒：未来 3 个完整小时内天气相对安全，降雨概率较低。\n"
        if rain_duration > 0:
            analysis += f"💡 提示：虽然近3小时无雨，但后续时段有降雨预警，**建议出门仍随身携带便携雨伞以防万一**。\n\n"
        else:
            analysis += f"💡 提示：未来半天无降雨风险，出门无需带伞，可以尽情享受校园生活。\n\n"

    # --- 12小时持续性与开始时间（修复点 4：防止输出“已过时的开始时间”） ---
    if rain_duration > 0 and rain_start_index != -1:
        # 【关键修复】如果开始索引 <= 当前索引，说明降雨已经开始
        if rain_start_index <= current_index + 1:
            start_desc = "🌧️ 降雨已经开始了，请立即做好防雨准备"
        else:
            raw_start_time = times[rain_start_index]
            formatted_start_time = format_forecast_time(raw_start_time, now_beijing)
            start_desc = f"🌧️ 降雨预计最快会于 **{formatted_start_time}** 左右开始"

        analysis += (
            f"🌧️ 持续时间预测：未来 12 个完整小时内，预计会累计出现约 {rain_duration} 个小时的降水。\n"
            f"{start_desc}，请注意防范。\n\n"
        )
    else:
        analysis += (
            f"☀️ 持续时间预测：未来 12 个完整小时内武大校区无连续降雨时段，"
            f"非常适合去九一二操场或者教五大草坪散步。\n\n"
        )

    # --- 温度与穿衣防晒建议 ---
    analysis += f"🌡️ 温度与穿衣提示：当前气温为 {current_temp:.1f}℃。\n"
    analysis += f"未来 12 个小时内最低气温 {min_temp:.1f}℃，最高气温 {max_temp:.1f}℃（昼夜温差约 {temp_diff:.1f}℃）。\n"

    if temp_diff >= 8.0:
        analysis += "👚 穿衣建议：武大今天温差较大，早晚偏凉，建议采用洋葱式穿衣法（内里短袖/衬衫，外搭一件轻薄外套），方便根据气温增减。\n"
    elif max_temp >= 30.0:
        analysis += "🌞 防晒建议：天气较热，紫外线较强，出门请注意涂抹防晒霜，并在包里备好防晒帽或晴雨伞。\n"
    else:
        analysis += "🧥 穿衣建议：温度适宜，穿着普通的春秋装（如长袖T恤、卫衣、牛仔裤）即可舒适出行。\n"

    return analysis


# ==========================================
# 本地测试入口
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("开始获取武汉大学精准天气降雨分析...")
    print("=" * 60)
    report = get_whu_rain_forecast.invoke({})
    print("\n" + report)
    print("\n" + "=" * 60)
    print("测试完成。")
    print("=" * 60)