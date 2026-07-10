"""
CAS 多方式登录 — 密码 / QR码 / 动态短信，纯 HTTP

用法:
    from cas_login import CasClient

    client = CasClient()

    # 密码登录
    castgc = client.login_password("学号", "密码")

    # QR 码登录
    img_b64 = client.qr_get_image()
    castgc = client.qr_poll()  # 阻塞等待扫码

    # 短信登录
    client.sms_send("手机号")
    castgc = client.sms_verify("验证码")
"""

import re
import time
import base64
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

CAS = "https://cas.whu.edu.cn/authserver"


class CasClient:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.verify = False
        self.sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self._execution = ""
        self._pwd_salt = ""
        self._qr_uuid = ""

    # ── 通用 ─────────────────────────────────

    def _get_login_page(self):
        """获取登录页，提取 execution 和 pwdEncryptSalt"""
        resp = self.sess.get(f"{CAS}/login", timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        self._execution = (soup.find("input", {"name": "execution"}) or {}).get("value", "")
        salt_el = soup.find("input", {"id": "pwdEncryptSalt"})
        self._pwd_salt = salt_el.get("value", "") if salt_el else ""
        return resp

    def _extract_castgc(self, resp=None) -> str | None:
        """从响应 Set-Cookie 或 session cookies 提取 CASTGC"""
        # 优先从响应头
        if resp is not None:
            m = re.search(r"CASTGC=(TGT-[^;]+)", resp.headers.get("Set-Cookie", ""))
            if m:
                return m.group(1)
        # 从 session cookies
        return self.sess.cookies.get("CASTGC") or None

    # ── 密码登录 ─────────────────────────────

    def login_password(self, username: str, password: str) -> str | None:
        """密码登录，返回 CASTGC"""
        # 每次密码登录用新 session（避免 QR/短信的 session 污染）
        self.sess = requests.Session()
        self.sess.verify = False
        self.sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self._get_login_page()

        from cas_encrypt import encrypt_password
        encrypted = encrypt_password(password, self._pwd_salt)

        resp = self.sess.post(
            f"{CAS}/login",
            data={
                "username": username,
                "password": encrypted,
                "execution": self._execution,
                "_eventId": "submit",
                "cllt": "userNameLogin",
                "dllt": "generalLogin",
            },
            allow_redirects=False,
            timeout=15,
        )
        print(f"[CAS] POST → status={resp.status_code} Location={resp.headers.get('Location','')[:80]}")
        return self._extract_castgc(resp)

    # ── QR 码登录 ────────────────────────────

    def qr_get_image(self) -> str | None:
        """获取 QR 码图片 (base64 PNG)，用于在 Streamlit 中显示"""
        self._get_login_page()

        # 获取 QR token
        resp = self.sess.get(f"{CAS}/qrCode/getToken", params={"ts": int(time.time() * 1000)})
        self._qr_uuid = resp.text.strip()
        if not self._qr_uuid.startswith("QR-"):
            return None

        # 获取 QR 码图片
        resp = self.sess.get(f"{CAS}/qrCode/getCode", params={"uuid": self._qr_uuid})
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode()
        return None

    def qr_poll(self, timeout: int = 120) -> str | None:
        """
        轮询 QR 码扫码状态，返回 CASTGC。
        阻塞直到扫码成功或超时。
        """
        if not self._qr_uuid:
            return None

        submitted = False  # 只提交一次
        for _ in range(timeout * 2):
            resp = self.sess.get(
                f"{CAS}/qrCode/getStatus.htl",
                params={"uuid": self._qr_uuid, "ts": int(time.time() * 1000)},
            )
            status = resp.text.strip()
            castgc = self._extract_castgc(resp)
            if castgc:
                return castgc

            if status == "1" and not submitted:
                submitted = True
                print("[QR] 确认成功，提交 qrLoginForm...")
                # 浏览器 JS: $("#qrLoginForm").submit()
                # 表单字段: lt, uuid(QR token), cllt=qrLogin, dllt=generalLogin, execution, _eventId, rmShown
                resp2 = self.sess.post(
                    f"{CAS}/login",
                    data={
                        "lt": "",
                        "uuid": self._qr_uuid,
                        "cllt": "qrLogin",
                        "dllt": "generalLogin",
                        "execution": self._execution,
                        "_eventId": "submit",
                        "rmShown": "1",
                    },
                    allow_redirects=False,
                    timeout=15,
                )
                print(f"[QR] POST form → status={resp2.status_code} Location={str(resp2.headers.get('Location',''))[:120]}")
                castgc = self._extract_castgc(resp2)
                if castgc:
                    return castgc
                # 跟重定向
                if resp2.status_code in (301, 302, 303, 307, 308):
                    loc = resp2.headers.get("Location", "")
                    if loc:
                        resp3 = self.sess.get(loc if loc.startswith("http") else f"{CAS}{loc}" if loc.startswith("/") else f"{CAS}/{loc}",
                                             allow_redirects=False, timeout=15)
                        castgc = self._extract_castgc(resp3)
                        if castgc:
                            return castgc
            elif status == "2":
                print(f"[QR] 已扫码，等待确认...")
            time.sleep(0.5)

        return None  # 超时

    def qr_login(self, timeout: int = 120) -> str | None:
        """一步完成：获取 QR → 轮询 → 返回 CASTGC"""
        img = self.qr_get_image()
        if not img:
            return None
        return self.qr_poll(timeout)

    # ── 短信/动态码登录 ─────────────────────

    def sms_get_captcha(self) -> str | None:
        """获取图形验证码图片（base64 PNG），可能不需要"""
        self.sess = requests.Session()
        self.sess.verify = False
        self.sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self._get_login_page()
        resp = self.sess.get(f"{CAS}/getCaptcha.htl", params={"_": int(time.time() * 1000)})
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode()
        return None

    def sms_send(self, phone: str, captcha_text: str) -> str | None:
        """
        发送短信验证码到手机号。需跟 sms_get_captcha 用同一个 CasClient。
        """
        DEFAULT_SALT = "rjBFAaHsNkKAhpoi"
        from cas_encrypt import encrypt_password

        # 直接发，captcha 从 sms_get_captcha 获取
        encrypted_phone = encrypt_password(phone, DEFAULT_SALT)
        resp = self.sess.post(
            f"{CAS}/dynamicCode/getDynamicCode.htl",
            data={"mobile": encrypted_phone, "captcha": captcha_text},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{CAS}/login",
            },
            timeout=15,
        )
        print(f"[SMS send] → body={resp.text[:200]}")
        try:
            return resp.json().get("message", resp.text)
        except Exception:
            return resp.text

    def sms_login(self, phone: str, code: str) -> str | None:
        """
        用短信验证码登录，返回 CASTGC。
        """
        from cas_encrypt import encrypt_password
        encrypted_code = encrypt_password(code, self._pwd_salt)

        resp = self.sess.post(
            f"{CAS}/login",
            data={
                "username": phone,
                "password": encrypted_code,
                "execution": self._execution,
                "_eventId": "submit",
                "cllt": "dynamicLogin",
                "dllt": "generalLogin",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{CAS}/login"},
            allow_redirects=False,
            timeout=15,
        )
        print(f"[SMS login] → status={resp.status_code} Location={str(resp.headers.get('Location',''))[:80]}")
        return self._extract_castgc(resp)


if __name__ == "__main__":
    import sys

    client = CasClient()

    if len(sys.argv) >= 3 and sys.argv[1] == "password":
        castgc = client.login_password(sys.argv[2], sys.argv[3])
        print(f"CASTGC={castgc}" if castgc else "登录失败")

    elif len(sys.argv) >= 2 and sys.argv[1] == "qr":
        print("获取 QR 码...")
        img = client.qr_get_image()
        if img:
            # 保存为文件查看
            with open("qr_code.png", "wb") as f:
                f.write(base64.b64decode(img))
            print("QR 码已保存到 qr_code.png，请扫码")
            print("等待扫码...")
            castgc = client.qr_poll(timeout=120)
            print(f"CASTGC={castgc}" if castgc else "超时")
        else:
            print("获取 QR 码失败")

    elif len(sys.argv) >= 2 and sys.argv[1] == "sms":
        phone = sys.argv[2] if len(sys.argv) > 2 else input("手机号: ")
        img = client.sms_get_captcha()
        if img:
            with open("sms_captcha.png", "wb") as f:
                f.write(base64.b64decode(img))
            print(f"验证码已保存到 sms_captcha.png，手机号: {phone}")
        captcha = input("图形验证码（不需要验证码直接回车）: ").strip()
        if not captcha:
            print("跳过验证码，直接尝试发送...")
        result = client.sms_send(phone, captcha)
        print(f"发送结果: {result}")
        if "成功" not in str(result) and "success" not in str(result).lower():
            print("可重新运行尝试")
            sys.exit(1)
        code = input("请输入收到的短信验证码: ")
        castgc = client.sms_login(phone, code)
        print(f"CASTGC={castgc}" if castgc else "登录失败")

    else:
        print("用法:")
        print("  python cas_login.py password 学号 密码")
        print("  python cas_login.py qr")
        print("  python cas_login.py sms [手机号]")
