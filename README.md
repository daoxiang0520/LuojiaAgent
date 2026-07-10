# LuojiaAgent — 武大校园智能助手

基于 **LangGraph + DeepSeek V4 Pro** 的多智能体系统，覆盖课表、成绩、考试、图书馆座位、天气五大校园场景。

## 架构

```
Streamlit 前端 ←→ LangGraph Agent (DeepSeek V4 Pro + 深度思考)
                      │
            ┌─────────┼─────────┐
            ▼         ▼         ▼
        login_helper  courses   library
        (CAS 登录)    grades    weather
                      exams
```

- **LLM**: `deepseek-v4-pro`（支持 thinking + function calling 一体）
- **Agent**: LangGraph `StateGraph`，MemorySaver 会话管理
- **前端**: Streamlit，日/夜双主题，语音朗读

## 工具列表

| 工具 | 功能 | 认证 |
|:---|:---|:---|
| `login_to_whu_portal` | CAS 统一身份认证 | Playwright 弹窗登录 |
| `query_whu_schedule` | 课表查询 | 教务 JSESSIONID |
| `query_whu_grades_realtime` | 成绩查询 | 教务 JSESSIONID |
| `query_whu_exam_schedule` | 考试安排 | 教务 JSESSIONID |
| `query_library_seats` | 分馆座位大盘 | HMAC 签名 |
| `query_empty_seats_in_area` | 区域座位图 | HMAC 签名 |
| `reserve_library_seat` | 预约座位（自动破解验证码） | HMAC 签名 |
| `query_user_reservations` | 预约记录 | HMAC 签名 |
| `cancel_library_reservation` | 取消预约 | HMAC 签名 |
| `get_current_usage` | 当前使用中座位 | HMAC 签名 |
| `stop_library_usage` | 签退释放 | HMAC 签名 |
| `get_whu_rain_forecast` | 珞珈山天气 | 无 |

## 快速开始

### 1. 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. 配置 API Key

```bash
echo "sk-your-deepseek-key" > api.key
```

### 3. 启动

```bash
streamlit run app.py
```

### Docker

```bash
docker compose up -d
```

## 项目结构

```
LuojiaAgent/
├── agent.py              # LangGraph 智能体（StateGraph + LLM + 路由）
├── app.py                # Streamlit 前端
├── api.key               # DeepSeek API 密钥
├── requirements.txt      # Python 依赖
├── Dockerfile            # Docker 镜像
├── docker-compose.yml    # 一键部署
│
└── tools/
    ├── __init__.py        # 工具统一导出（ALL_TOOLS）
    ├── login_helper.py    # CAS 登录 + 凭证收割
    ├── courses_tool.py    # 课表查询
    ├── grades_tool.py     # 成绩查询
    ├── exam_tool.py       # 考试安排
    ├── library_tool.py    # 图书馆全套（HMAC 签名 + 验证码破解 + CAS SSO）
    ├── weather_tool.py    # Open-Meteo 天气
    ├── captcha_solver.py  # TAC 验证码破解（OpenCV + AES/RSA）
    └── captcha_refs.npz   # 验证码参考图库
```

## 图书馆 API 技术细节

### 认证链路

```
CAS 登录 → CASTGC → 图书馆 OAuth → JWT → auth/cas → sessionStorage token + hmacKey
```

### HMAC 签名

```
sign_str = "seat::{UUID}::{timestamp_ms}::{METHOD}"
signature = HMAC-SHA256(sign_str, hmacKey).hex()
```

`hmacKey` 以 AES-128-CBC 加密存储在 `sessionStorage['jsq_p-systemInfo']`，解密密钥 `server_date_time`、IV `client_date_time`。

### 调用策略

- **Layer 1**: 纯 HTTP + HMAC 签名（~0.5s）
- **Layer 2**: Playwright headless 刷新凭证（~5s，token 过期时）

## 反向代理项目

图书馆 API 逆向分析、验证码破解、HMAC 算法详见 [whu-lib-api](https://github.com/daoxiang0520/whu-lib-api)。

## License

MIT
