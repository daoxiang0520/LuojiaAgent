# tools/__init__.py

# 1. 导入各个子模块中的工具函数
# (请根据组员代码中实际的函数名进行修改)
from .login_helper import login_to_whu_portal
from .courses_tool import query_whu_schedule
from .library_tool import query_library_seats
from .library_tool import query_empty_seats_in_area
from .library_tool import reserve_library_seat
from .library_tool import query_user_reservations
from .library_tool import cancel_library_reservation
from .library_tool import get_current_usage
from .library_tool import stop_library_usage
from .weather_tool import get_whu_rain_forecast
from .grades_tool import query_whu_grades_realtime
from .exam_tool import query_whu_exam_schedule

# 2. 统一打包成一个列表，方便 agent.py 一键导入
ALL_TOOLS = [
    login_to_whu_portal,
    query_whu_schedule,
    query_library_seats,
    get_whu_rain_forecast,
    query_whu_grades_realtime,
    query_empty_seats_in_area,
    reserve_library_seat,
    query_user_reservations,
    cancel_library_reservation,
    get_current_usage,
    stop_library_usage,
    query_whu_exam_schedule,
]
# 3. 暴露给外部
__all__ = ["ALL_TOOLS"]