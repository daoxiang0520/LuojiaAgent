# 修改时间 26/7/8 9:22

## 📖 `login_helper.py` 接口文档

### 1. 工具概述

`login_helper.py` 提供了一个**交互式登录收割工具**，通过 Playwright 启动浏览器，引导用户完成智慧珞珈统一身份认证，并自动收割**智慧珞珈（zhlj）**、**本科教务系统（jwgl）** 和**图书馆自习室**三端的独立 Cookie 凭证。

---

### 2. 函数签名

```python
def interactive_whu_login() -> dict
```

```python
@tool
def login_to_whu_portal(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command
```

---

### 3. 返回值结构

`interactive_whu_login()` 返回一个 **字典（dict）**，包含以下字段：

| 字段名 | 类型 | 说明 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **`cookie_str`** | `str` | 智慧珞珈门户（`zhlj.whu.edu.cn`）的完整 Cookie 字符串 | 课表查询、智慧珞珈 API 调用 |
| **`jwgl_cookie_str`** | `str` | 本科教务系统（`jwgl.whu.edu.cn`）的完整 Cookie 字符串 | **成绩查询**、选课、课表等教务功能 |
| **`library_token`** | `str` | 图书馆自习室的 48 位短 Token | 图书馆选座、自习室预约 API |
| **`library_jwt_token`** | `str` | 图书馆系统的 JWT 授权长密钥 | 图书馆系统鉴权（备用） |
| **`library_hmac`** | `str` | 图书馆请求的 HMAC 签名密钥 | 图书馆 API 请求签名（高级） |
| **`library_request_date`** | `str` | 图书馆请求的时间戳 | 配合 HMAC 使用 |
| **`library_request_id`** | `str` | 图书馆请求的唯一 ID | 配合 HMAC 使用 |

**示例返回值：**

```python
{
    "cookie_str": "route=xxx; PORTAL-TOKEN=eyJhbGci...; zhlj_authorization=xxx; JSESSIONID=xxx",
    "jwgl_cookie_str": "JSESSIONID=D068F7B48ABB89E74EEC5797D6B0374; SF_cookie_1=41112036; _dx_captcha_vid=sl2gqgzvtmra95vjt; _dx_uzZo5y=177241...",
    "library_token": "13ff24f95109ae7c9483d26cd77703bf3c5f165f08083633",
    "library_jwt_token": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiO...",
    "library_hmac": "...",
    "library_request_date": "...",
    "library_request_id": "..."
}
```

---

### 4. 调用方式

#### 方式一：本地测试/调试（直接调用）

```python
from login_helper import interactive_whu_login

result = interactive_whu_login()

# 获取教务系统 Cookie（供成绩工具使用）
jwgl_cookie = result["jwgl_cookie_str"]
print(jwgl_cookie)

# 获取智慧珞珈 Cookie（供课表工具使用）
zhlj_cookie = result["cookie_str"]
print(zhlj_cookie)
```

#### 方式二：LangGraph Agent 中调用（工具调用）

```python
from login_helper import login_to_whu_portal

# 在 LangGraph 的 ToolNode 中，由大模型自动调用
# 或者手动调用：
command = login_to_whu_portal.invoke({"tool_call_id": "some_id"})

# 返回的 Command 对象包含 update 字段
# 会将完整的 credentials 字典写入 state["cookie_str"]
```

---

### 5. 在 LangGraph State 中的存储

`login_to_whu_portal` 返回的 `Command` 会将完整的凭证字典存入 `state["cookie_str"]`。

**AgentState 定义：**

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    cookie_str: dict  # 存储完整凭证字典
```

**各工具提取对应的 Cookie：**

```python
# 成绩查询工具（需要教务系统 Cookie）
def query_whu_grades(state: dict) -> str:
    cookie_data = state.get("cookie_str", {})
    if isinstance(cookie_data, dict):
        jwgl_cookie = cookie_data.get("jwgl_cookie_str", "")
    else:
        jwgl_cookie = cookie_data
    # 使用 jwgl_cookie 进行请求...

# 课表查询工具（需要智慧珞珈 Cookie）
def get_whu_schedule(state: dict) -> str:
    cookie_data = state.get("cookie_str", {})
    if isinstance(cookie_data, dict):
        zhlj_cookie = cookie_data.get("cookie_str", "")  # 注意：智慧珞珈存在 cookie_str 键中
    else:
        zhlj_cookie = cookie_data
    # 使用 zhlj_cookie 进行请求...

# 图书馆工具（需要自习室 Token）
def get_library_seat(state: dict) -> str:
    cookie_data = state.get("cookie_str", {})
    library_token = cookie_data.get("library_token", "")
    # 使用 library_token 进行请求...
```

---

### 6. Cookie 字段详情

#### 6.1 智慧珞珈 Cookie（`cookie_str`）

| Cookie 名称 | 说明 | 有效期 |
| :--- | :--- | :--- |
| `PORTAL-TOKEN` | **核心身份令牌**（JWT 格式） | 会话 |
| `zhlj_authorization` | 智慧珞珈授权凭证 | 会话 |
| `JSESSIONID` | 会话 ID | 会话 |
| `route` | 路由/负载均衡标识 | 会话 |

#### 6.2 教务系统 Cookie（`jwgl_cookie_str`）

| Cookie 名称 | 说明 | 有效期 |
| :--- | :--- | :--- |
| `JSESSIONID` | **核心会话凭证**（必须） | 会话 |
| `SF_cookie_1` | 负载均衡/会话标识 | 会话 |
| `_dx_captcha_vid` | 顶象验证码会话 ID | 长期 |
| `_dx_uzZo5y` | 顶象验证码用户标识 | 长期 |

> **注意**：成绩查询工具只需要 `JSESSIONID` 和 `SF_cookie_1`，顶象 Cookie 为可选。

#### 6.3 图书馆凭证

| 字段名 | 说明 |
| :--- | :--- |
| `library_token` | 48 位短 Token，用于自习室 API 鉴权 |
| `library_jwt_token` | JWT 长密钥，用于图书馆系统登录 |
| `library_hmac` | HMAC 签名密钥 |
| `library_request_date` | 请求时间戳 |
| `library_request_id` | 请求唯一 ID |

---

### 7. 调用示例（完整流程）

```python
# test_login.py

from login_helper import interactive_whu_login, login_to_whu_portal

# ========== 方式 1：直接调用（调试） ==========
print("=== 直接调用 interactive_whu_login ===")
result = interactive_whu_login()

print(f"智慧珞珈 Cookie: {result['cookie_str'][:50]}...")
print(f"教务系统 Cookie: {result['jwgl_cookie_str'][:50]}...")
print(f"自习室 Token: {result['library_token']}")


# ========== 方式 2：LangGraph 工具调用 ==========
print("\n=== LangGraph 工具调用 ===")
command = login_to_whu_portal.invoke({"tool_call_id": "test_123"})

# 从 Command 的 update 中获取凭证
credentials = command.update.get("cookie_str", {})
print(f"教务系统 Cookie: {credentials.get('jwgl_cookie_str', '')[:50]}...")


# ========== 方式 3：直接用于成绩查询 ==========
from grades_demo import query_whu_grades_realtime

result = interactive_whu_login()
jwgl_cookie = result["jwgl_cookie_str"]

# 传入成绩工具
grades_report = query_whu_grades_realtime.invoke({
    "cookie_str": jwgl_cookie  # 直接传入教务系统 Cookie 字符串
})
print(grades_report)
```

---

### 8. 错误处理

```python
try:
    result = interactive_whu_login()
except TimeoutError as e:
    print(f"登录超时: {e}")
except Exception as e:
    print(f"登录失败: {e}")
```

---

### 9. 性能参数

| 环节 | 默认超时 | 说明 |
| :--- | :--- | :--- |
| 登录等待 | 120 秒 | 用户扫码/输入密码 |
| 图书馆流转 | 10 秒 | OAuth 重定向等待 |
| 新标签页检测 | 20 秒 | 点击后等待跳转 |
| 网络空闲 | 15 秒 | 等待教务系统加载 |
| 顶象初始化 | 3 秒 | 等待验证码脚本 |

---

### 10. 注意事项

1. **Cookie 有效期**：`JSESSIONID` 为会话级 Cookie，关闭浏览器即失效，建议每次使用前重新获取。
2. **多工具协同**：成绩工具使用 `jwgl_cookie_str`，课表工具使用 `cookie_str`（智慧珞珈），不要混用。
3. **浏览器模式**：`headless=False` 必须保持，因为需要用户手动扫码登录。
4. **顶象 Cookie**：不是必需的，如果只需要成绩查询，`_dx_captcha_vid` 和 `_dx_uzZo5y` 可以缺失。