"""
CAS 反向代理 — 镜像 cas.whu.edu.cn 登录页，截获 CASTGC

用法:
    python cas_proxy.py
    → 浏览器打开 http://localhost:8765
    → 正常登录 CAS → 代理自动截获 CASTGC → harvest 图书馆+教务
"""

import re
import json
import threading
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from flask import Flask, request, Response, redirect

urllib3.disable_warnings()

CAS_SERVER = "https://cas.whu.edu.cn"
PROXY_HOST = "localhost"
PROXY_PORT = 8765

app = Flask(__name__)

# ── 存储截获的 CASTGC ──
captured_castgc = None
capture_event = threading.Event()

# ── 每个用户维护一个持久 Session，保留 CAS 的 JSESSIONID ──
from collections import defaultdict
_user_sessions = defaultdict(requests.Session)
for s in _user_sessions.values():
    s.verify = False


def _get_user_id():
    """用 IP + User-Agent 简单区分用户"""
    ua = request.headers.get("User-Agent", "")
    ip = request.remote_addr
    return f"{ip}|{ua[:60]}"


def _proxy_request(method, path, headers, data, params):
    """转发请求到 CAS，返回响应"""
    url = urljoin(CAS_SERVER, path)
    sess = _user_sessions[_get_user_id()]

    # 清理不需要转发的 header
    forward_headers = {}
    skip = {"host", "content-length", "connection", "accept-encoding"}
    for k, v in headers.items():
        if k.lower() not in skip and not k.lower().startswith("x-forwarded"):
            forward_headers[k] = v
    forward_headers["Host"] = "cas.whu.edu.cn"

    resp = sess.request(
        method=method, url=url,
        headers=forward_headers,
        params=params,
        data=data,
        allow_redirects=False,  # 关键：不跟重定向，自己处理
        timeout=15,
    )

    # 检测 Set-Cookie 中的 CASTGC
    set_cookie = resp.headers.get("Set-Cookie", "")
    castgc_match = re.search(r"CASTGC=([^;]+)", set_cookie)
    if castgc_match:
        global captured_castgc
        captured_castgc = castgc_match.group(1)
        capture_event.set()
        print(f"\n🎉 截获 CASTGC: {captured_castgc[:40]}...\n")

    # 调试：QR 轮询响应体
    if "getStatus" in path or "qrCode" in path:
        body_preview = resp.text[:300] if resp.text else "(empty)"
        print(f"[DEBUG] {path} | Set-Cookie={bool(set_cookie)} | body={body_preview}")
    if "checkNeedCaptcha" in path:
        print(f"[DEBUG] checkNeedCaptcha response: {resp.text[:200]}")
    if "login" in path and method == "POST":
        print(f"[DEBUG] Login POST → status={resp.status_code} Location={resp.headers.get('Location','')} Set-Cookie={set_cookie[:100]}")

    return resp


def _rewrite_html(html: str) -> str:
    """改写 CAS 登录页的 URL，指向代理。跳过 javascript: data: mailto:"""
    # 替换 action URL
    html = html.replace(
        'action="/authserver/login',
        f'action="http://{PROXY_HOST}:{PROXY_PORT}/authserver/login'
    )
    # 替换绝对 URL
    html = html.replace(
        f'{CAS_SERVER}/',
        f'http://{PROXY_HOST}:{PROXY_PORT}/'
    )
    # 替换相对路径资源（跳过 javascript: data: mailto: #）
    html = re.sub(
        r'(src|href)=["\'](?!/)(?!(?:https?:|//|javascript:|data:|mailto:|#))',
        rf'\1="http://{PROXY_HOST}:{PROXY_PORT}/',
        html
    )
    return html


def _rewrite_location(location: str) -> str:
    """改写 302 Location 头，指向代理"""
    if location.startswith(CAS_SERVER):
        return location.replace(CAS_SERVER, f"http://{PROXY_HOST}:{PROXY_PORT}")
    return location


@app.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/<path:path>", methods=["GET", "POST"])
def proxy(path=""):
    global captured_castgc

    # 如果已截获 CASTGC，显示成功页
    if captured_castgc:
        return f"""
        <html><head><meta charset="utf-8"><title>登录成功</title>
        <style>body{{font-family:sans-serif;display:flex;justify-content:center;align-items:center;
        height:100vh;margin:0;background:#f5f5f5}}
        .box{{background:#fff;padding:40px;border-radius:12px;box-shadow:0 2px 20px rgba(0,0,0,0.1);
        text-align:center;max-width:500px}}
        .key{{background:#f0f0f0;padding:10px;border-radius:4px;word-break:break-all;font-family:monospace;
        font-size:12px;margin:16px 0}}</style></head><body>
        <div class="box">
        <h2>✅ CAS 登录成功</h2>
        <p>CASTGC 已截获：</p>
        <div class="key">{captured_castgc}</div>
        <p style="color:#666;font-size:14px">代理已将凭证转发给后台处理<br>你现在可以关闭此页面，
        <a href="http://localhost:8501">返回 LuojiaAgent</a></p>
        </div></body></html>
        """

    full_path = f"/{path}" if path else "/"
    if request.query_string:
        full_path += f"?{request.query_string.decode()}"

    method = request.method
    headers = dict(request.headers)
    data = request.get_data() or None
    params = request.args.to_dict() or None

    if method == "POST" and "login" in path:
        data_preview = (request.get_data() or b"").decode("utf-8", errors="replace")[:300]
        print(f"[proxy] {method} {full_path} body={data_preview}")
    else:
        print(f"[proxy] {method} {full_path}")

    try:
        resp = _proxy_request(method, full_path, headers, data, params)
    except Exception as e:
        return f"代理错误: {e}", 502

    # 处理重定向
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        new_location = _rewrite_location(location)
        return redirect(new_location, code=resp.status_code)

    # 改写 HTML
    content_type = resp.headers.get("Content-Type", "")
    body = resp.content

    if "text/html" in content_type:
        body = _rewrite_html(body.decode("utf-8", errors="replace")).encode()

    # 只返回我们关心的 header
    proxy_resp = Response(body, status=resp.status_code)
    for k, v in resp.headers.items():
        if k.lower() in ("content-type", "content-length", "set-cookie", "location"):
            proxy_resp.headers[k] = v

    return proxy_resp


@app.route("/status")
def status():
    """查询是否已截获 CASTGC"""
    if captured_castgc:
        return {"status": "ok", "castgc": captured_castgc}
    return {"status": "waiting"}


@app.route("/reset")
def reset():
    """清除 CASTGC（重新登录）"""
    global captured_castgc
    captured_castgc = None
    capture_event.clear()
    return redirect("/authserver/login")


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════╗
║     CAS 反向代理                          ║
║                                          ║
║  浏览器打开: http://{PROXY_HOST}:{PROXY_PORT}   ║
║  正常登录 CAS → 代理自动截 CASTGC           ║
╚══════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=PROXY_PORT, debug=True)
