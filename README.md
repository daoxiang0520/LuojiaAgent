# LuojiaAgent — 武大校园智能助手

基于 **LangGraph + DeepSeek V4 Pro** 的多智能体系统。覆盖课表、成绩、考试、图书馆座位、天气五大校园场景。

## 特性

- **零浏览器登录** — 密码/QR 码纯 HTTP 登录 CAS，无需弹窗
- **HMAC 签名** — 纯 Python 复现图书馆 API 签名，~0.5s 响应
- **三层 fallback** — 缓存优先 → 过期自动刷新 → 友好报错
- **自动收割** — 登录后自动获取图书馆 token + 教务 Cookie
- **主动规划** — LLM 会查课表、天气、座位后综合建议

## 快速开始

```bash
# 一键安装
git clone https://github.com/daoxiang0520/LuojiaAgent.git
cd LuojiaAgent
bash setup.sh

# 或 pip
pip install git+https://github.com/daoxiang0520/LuojiaAgent.git

# 启动
streamlit run app.py
```

### Docker

```bash
docker compose up -d
```

## 登录方式

| 方式 | 适用场景 | 是否需要浏览器 |
|:---|:---|:---|
| 🔑 密码登录 | 知道学号密码 | ❌ 纯 HTTP |
| 📱 扫码登录 | 不想输密码 | ❌ 显示 QR 码 |
| 🌐 浏览器弹窗 | 备用/开发调试 | ✅ Playwright |

## 工具列表

| 工具 | 功能 | 认证 |
|:---|:---|:---|
| `login_to_whu_portal` | CAS 统一身份认证 | 密码 / QR / 弹窗 |
| `query_whu_schedule` | 课表查询 | 教务 JSESSIONID |
| `query_whu_grades_realtime` | 成绩查询 | 教务 JSESSIONID |
| `query_whu_exam_schedule` | 考试安排 | 教务 JSESSIONID |
| `query_library_seats` | 分馆座位大盘 | HMAC 签名 |
| `query_empty_seats_in_area` | 区域座位图 | HMAC 签名 |
| `reserve_library_seat` | 预约座位（自动破解验证码） | HMAC 签名 |
| `query_user_reservations` | 预约记录（三源合并） | HMAC 签名 |
| `cancel_library_reservation` | 取消预约 | HMAC 签名 |
| `get_current_usage` | 当前使用中座位 | HMAC 签名 |
| `stop_library_usage` | 签退释放 | HMAC 签名 |
| `get_whu_rain_forecast` | 珞珈山天气 | 无 |

## 架构

```
Streamlit 前端 ←→ LangGraph Agent (DeepSeek V4 Pro + 深度思考)
                      │
            ┌─────────┼─────────────┐
            ▼         ▼             ▼
        login_helper  courses       library
        (密码/QR/弹窗) grades       weather
        cas_login.py  exams
        cas_encrypt.py
```

## 项目结构

```
LuojiaAgent/
├── agent.py              # LangGraph 智能体
├── app.py                # Streamlit 前端
├── pyproject.toml        # pip 安装配置
├── setup.sh              # 一键安装脚本
├── Dockerfile
├── docker-compose.yml
├── cas_login.py          # CAS HTTP 多种登录
├── cas_encrypt.py        # 密码 AES 加密
└── tools/
    ├── __init__.py
    ├── login_helper.py   # CASTGC 收割图书馆+教务
    ├── library_tool.py   # 图书馆全套（HMAC+验证码+CAS SSO）
    ├── courses_tool.py   # 课表
    ├── grades_tool.py    # 成绩
    ├── exam_tool.py      # 考试
    ├── weather_tool.py   # 天气
    ├── captcha_solver.py # TAC 验证码破解
    └── captcha_refs.npz  # 参考图库
```

## 图书馆 API 技术细节

### 认证链路

```
CAS 登录 → CASTGC → 图书馆 OAuth → JWT → auth/cas → sessionStorage token + hmacKey
```

### HMAC 签名

```
sign_str = "seat::{UUID}::{timestamp_ms}::{METHOD}"
signature = HMAC-SHA256(sign_str, decrypted_hmacKey).hex()
```

`hmacKey` 以 AES-128-CBC 加密（key=`server_date_time`, IV=`client_date_time`），解密后实测为 `whu2024lib`。

### 调用策略

| 层级 | 方式 | 速度 | 使用条件 |
|:---|:---|:---|:---|
| Layer 1 | 纯 HTTP + HMAC | ~0.5s | token 未过期 |
| Layer 2 | Playwright harvest | ~5s | token 过期，CASTGC 有效 |
| Layer 3 | 提示重新登录 | — | 全部过期 |

### 预约查询三源合并

`query_user_reservations` 合并三个 API 的结果：
- `currentUseMake` — 已签到入座
- `user/lastMake` — 今日预约（活跃 + 取消）
- `user/history` — 历史记录

## 反向代理项目

图书馆 API 逆向分析详见 [whu-lib-api](https://github.com/daoxiang0520/whu-lib-api)。

## 部署

```bash
# pip 安装
pip install git+https://github.com/daoxiang0520/LuojiaAgent.git

# GitHub Release
git tag v2.0.0 && git push --tags  # Actions 自动构建

```

## License

MIT
