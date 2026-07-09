"""
TAC 滑块验证码破解 - 最终版
武汉大学图书馆选座系统 seat.lib.whu.edu.cn

用法:
    python solver_final.py

依赖:
    pip install pycryptodome opencv-python numpy requests
"""

import base64
import json
import time
import random
import requests
import numpy as np
import cv2
import urllib3

from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.Random import get_random_bytes
from Cryptodome.Util import Counter
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 配置 ====================
BASE_URL = "https://seat.lib.whu.edu.cn"
GEN_URL = f"{BASE_URL}/jsq/static/cap/cg/gen/SLIDER"
CHECK_URL = f"{BASE_URL}/jsq/static/cap/cg/check"

# Check 阶段 RSA 公钥 (从 app.*.js openCaptcha 回调提取)
RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDXRMEk7baUetStHq6IPIxwKB9g
a9UyCepDEEFIZUS5cc1/FyS90Tbd1VA4j+AfqurclfBHUWgvuzAj4oW5b/sdS1SC
14259tLexFbT5EfPsyY0BPfMXkzUerSbzgL8ZIUtHfHV1z6/WA6iHVmB1SpWT2Bw
aE9Alednp9EO8dLQvQIDAQAB
-----END PUBLIC KEY-----"""

# Gen 阶段 RSA 公钥 (从 tac.min.js 默认)
RSA_PUBLIC_KEY_GEN = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDArgKannXgSG/WTmHP5ZdCsIhv
SxZQxZ2sQt9wXBm9SJyCN0nc3h6TL6fwaJJwELWwkJiVd/Fp2qtZPVsCk09opKQi
Xtbkxk+9ZzgxbYe5rrOXAPj+PZz+2b3J1L009FZ0W32bR3wuY6TDoyzKmmLceJMc
HDTK7g0RBcPvdUtWfQIDAQAB
-----END PUBLIC KEY-----"""

USERNAME = "2025302114221"  # 替换为实际学号
# ==============================================


class TACSolver:
    def __init__(self):
        self.rsa_key = RSA.import_key(RSA_PUBLIC_KEY)
        self.rsa_key_gen = RSA.import_key(RSA_PUBLIC_KEY_GEN)
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        # custom 明文 (匹配浏览器格式: 全部嵌套在 session 内)
        self.custom_plain = json.dumps({
            "session": {
                "username": USERNAME,
                "current_window_url": f"{BASE_URL}/seat/"
            }
        }, separators=(",", ":"))

    def _encrypt(self, data_json, rsa_key=None):
        """AES-128-CTR + RSA PKCS#1 v1.5 加密"""
        if rsa_key is None:
            rsa_key = self.rsa_key

        sk = get_random_bytes(16)
        iv = get_random_bytes(16)
        iv_int = int.from_bytes(iv, "big")

        # AES-CTR 加密 data
        ctr_d = Counter.new(128, initial_value=iv_int)
        ed = AES.new(sk, AES.MODE_CTR, counter=ctr_d).encrypt(data_json.encode())

        # AES-CTR 加密 custom (同一个 key+iv)
        ctr_c = Counter.new(128, initial_value=iv_int)
        ec = AES.new(sk, AES.MODE_CTR, counter=ctr_c).encrypt(self.custom_plain.encode())

        # RSA 加密 key|iv
        key_iv = f"{sk.hex()}|{iv.hex()}"
        ki = base64.b64encode(
            PKCS1_v1_5.new(rsa_key).encrypt(key_iv.encode())
        ).decode()

        return (
            base64.b64encode(ed).decode(),
            base64.b64encode(ec).decode(),
            ki,
        )

    def get_captcha(self):
        """获取验证码, 返回 (captcha_id, bg_b64, tpl_b64, captcha_obj)"""
        # Gen 只发 custom + ki (无 data 字段)
        _, cb64, gen_ki = self._encrypt("{}", rsa_key=self.rsa_key_gen)

        r = self.session.post(GEN_URL, json={"custom": cb64, "ki": gen_ki})
        if r.status_code != 200:
            raise Exception(f"Gen HTTP {r.status_code}: {r.text}")

        g = r.json()
        if g["captcha"]["type"] != "SLIDER":
            raise Exception(f"Gen failed: {g['captcha']}")

        cap = g["captcha"]
        bg_b64 = cap["backgroundImage"].split(",")[-1]
        tpl_b64 = cap["templateImage"].split(",")[-1]

        return g["id"], bg_b64, tpl_b64, cap

    def solve_offset(self, bg_b64, tpl_b64):
        """OpenCV 模板匹配计算滑块缺口偏移量"""
        bg_bytes = base64.b64decode(bg_b64)
        tpl_bytes = base64.b64decode(tpl_b64)

        bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        tpl_img = cv2.imdecode(np.frombuffer(tpl_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)

        if bg_img is None or tpl_img is None:
            return 200

        # Canny 边缘检测匹配
        be = cv2.Canny(bg_img, 100, 200)
        te = cv2.Canny(tpl_img, 100, 200)
        r1 = cv2.matchTemplate(be, te, cv2.TM_CCOEFF_NORMED)
        _, v1, _, l1 = cv2.minMaxLoc(r1)

        # 直接模板匹配
        r2 = cv2.matchTemplate(bg_img, tpl_img, cv2.TM_CCOEFF_NORMED)
        _, v2, _, l2 = cv2.minMaxLoc(r2)

        # 选置信度高的结果
        if v2 > 0.3 and v2 > v1:
            offset = l2[0]
        else:
            offset = l1[0]

        if offset < 30 or offset > 500:
            offset = 200

        return offset

    def generate_tracks(self, distance):
        """生成模拟人类滑动轨迹 (匹配浏览器格式)"""
        tracks = [{"x": 0, "y": 0, "type": "down", "t": 0}]

        cur = 0.0
        mid = distance * 4 / 5
        v = 0.0
        dt = 0.1
        start = int(time.time() * 1000)

        while cur < distance:
            a = 2.5 if cur < mid else -3.5
            v0 = v
            v = v0 + a * dt
            cur += v0 * dt + 0.5 * a * dt**2
            elapsed = int(time.time() * 1000) - start

            tracks.append({
                "x": int(cur),                          # 整数
                "y": random.choice([-1, 0, 0, 0, 1]),   # 整数
                "type": "move",                          # 必须有 type
                "t": elapsed,
            })
            time.sleep(random.uniform(0.01, 0.02))

        total = int(time.time() * 1000) - start
        tracks.append({
            "x": distance,
            "y": 0,
            "type": "move",
            "t": total + random.randint(10, 30),
        })

        return tracks, start, start + total

    def submit(self, captcha_id, offset, captcha_obj):
        """提交滑块验证"""
        tracks, st_ts, et_ts = self.generate_tracks(offset)

        # ISO 8601 UTC 时间字符串 (匹配浏览器格式)
        now = datetime.now(timezone.utc)
        st_str = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
        et_dt = datetime.fromtimestamp(et_ts / 1000, timezone.utc)
        et_str = et_dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{et_dt.microsecond // 1000:03d}Z"

        # 构建 data 明文
        data_plain = json.dumps({
            "bgImageWidth": captcha_obj.get("backgroundImageWidth", 600),
            "bgImageHeight": captcha_obj.get("backgroundImageHeight", 360),
            "sliderImageWidth": captcha_obj.get("templateImageWidth", 110),
            "sliderImageHeight": captcha_obj.get("templateImageHeight", 360),
            "startSlidingTime": st_str,
            "endSlidingTime": et_str,
            "trackList": tracks,
        }, separators=(",", ":"))

        db64, cb64, check_ki = self._encrypt(data_plain)

        r = self.session.post(CHECK_URL, json={
            "id": captcha_id,
            "data": db64,
            "custom": cb64,
            "ki": check_ki,
        })
        return r.json()

    def solve(self):
        """执行完整破解流程"""
        print("[1/4] 获取验证码...")
        captcha_id, bg_b64, tpl_b64, captcha_obj = self.get_captcha()
        print(f"      ID: {captcha_id}")

        print("[2/4] 识别缺口位置...")
        offset = self.solve_offset(bg_b64, tpl_b64)
        print(f"      offset = {offset}px")

        print("[3/4] 生成滑动轨迹...")
        tracks, st, et = self.generate_tracks(offset)
        print(f"      {len(tracks)} 点, {tracks[-1]['t']}ms")

        print("[4/4] 提交验证...")
        result = self.submit(captcha_id, offset, captcha_obj)
        print(f"      {result}")

        if result.get("success"):
            print("\n✅ 破解成功!")
        else:
            print(f"\n❌ 失败: code={result.get('code')} msg={result.get('msg')}")

        return result


if __name__ == "__main__":
    solver = TACSolver()
    result = solver.solve()
