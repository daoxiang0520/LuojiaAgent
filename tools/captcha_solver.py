"""
TAC 滑块验证码破解模块
武汉大学图书馆选座系统 seat.lib.whu.edu.cn

基于模式参考图差分 + AES-CTR/RSA 加密，5/5 成功率。
"""

import base64, json, time, random, os, numpy as np, cv2, urllib3, requests

from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.Random import get_random_bytes
from Cryptodome.Util import Counter
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://seat.lib.whu.edu.cn"
GEN_URL = f"{BASE_URL}/jsq/static/cap/cg/gen/SLIDER"
CHECK_URL = f"{BASE_URL}/jsq/static/cap/cg/check"

# RSA 公钥（Check 阶段）
RSA_PUBLIC_KEY_CHECK = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDXRMEk7baUetStHq6IPIxwKB9g
a9UyCepDEEFIZUS5cc1/FyS90Tbd1VA4j+AfqurclfBHUWgvuzAj4oW5b/sdS1SC
14259tLexFbT5EfPsyY0BPfMXkzUerSbzgL8ZIUtHfHV1z6/WA6iHVmB1SpWT2Bw
aE9Alednp9EO8dLQvQIDAQAB
-----END PUBLIC KEY-----"""

# RSA 公钥（Gen 阶段）
RSA_PUBLIC_KEY_GEN = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDArgKannXgSG/WTmHP5ZdCsIhv
SxZQxZ2sQt9wXBm9SJyCN0nc3h6TL6fwaJJwELWwkJiVd/Fp2qtZPVsCk09opKQi
Xtbkxk+9ZzgxbYe5rrOXAPj+PZz+2b3J1L009FZ0W32bR3wuY6TDoyzKmmLceJMc
HDTK7g0RBcPvdUtWfQIDAQAB
-----END PUBLIC KEY-----"""

# 参考库路径（与脚本同目录）
_REF_PATH = os.path.join(os.path.dirname(__file__), "captcha_refs.npz")

# 延迟加载参考库
_refs = None


def _load_refs():
    """加载模式参考图（惰性加载）"""
    global _refs
    if _refs is None:
        if os.path.exists(_REF_PATH):
            d = np.load(_REF_PATH)
            _refs = [
                {"sample_img": d["g0_sample"], "mode_bg": d["g0_mode"]},
                {"sample_img": d["g1_sample"], "mode_bg": d["g1_mode"]},
            ]
        else:
            raise FileNotFoundError(
                f"Reference file not found: {_REF_PATH}\n"
                "Run 'python build_reference.py' first to generate it."
            )
    return _refs


def _find_gap(bg_b64: str) -> int:
    """用参考库差分定位缺口位置"""
    refs = _load_refs()
    bg = cv2.imdecode(np.frombuffer(base64.b64decode(bg_b64), np.uint8), cv2.IMREAD_GRAYSCALE)
    bg_f = bg.astype(float)

    # 分类到最近布局组
    best_g = 0
    best_sim = 100
    for gi, ref in enumerate(refs):
        sim = np.mean(np.abs(bg_f - ref["sample_img"].astype(float)) > 30) * 100
        if sim < best_sim:
            best_sim = sim
            best_g = gi

    # 与模式参考图差分
    mode_bg = refs[best_g]["mode_bg"].astype(float)
    diff = np.abs(bg_f - mode_bg)
    col_diff = np.sum(diff, axis=0)
    smooth = np.convolve(col_diff, np.ones(15) / 15, mode="same")

    # 找 110px 窗口差值和最大的位置
    best_x = max(range(40, 470), key=lambda x: np.sum(smooth[x : x + 110]))
    return best_x


class CaptchaSolver:
    """TAC 滑块验证码破解器"""

    def __init__(self, username: str = "2025302114221"):
        self.rsa_key = RSA.import_key(RSA_PUBLIC_KEY_CHECK)
        self.username = username
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

    @property
    def _custom_plain(self):
        return json.dumps(
            {
                "session": {
                    "username": self.username,
                    "current_window_url": f"{BASE_URL}/seat/",
                }
            },
            separators=(",", ":"),
        )

    def _encrypt(self, data_json: str):
        """AES-128-CTR + RSA PKCS#1 v1.5"""

        sk = get_random_bytes(16)
        iv = get_random_bytes(16)
        iv_int = int.from_bytes(iv, "big")

        ctr_d = Counter.new(128, initial_value=iv_int)
        ctr_c = Counter.new(128, initial_value=iv_int)
        ed = AES.new(sk, AES.MODE_CTR, counter=ctr_d).encrypt(data_json.encode())
        ec = AES.new(sk, AES.MODE_CTR, counter=ctr_c).encrypt(
            self._custom_plain.encode()
        )

        key_iv = f"{sk.hex()}|{iv.hex()}"
        ki = base64.b64encode(
            PKCS1_v1_5.new(self.rsa_key).encrypt(key_iv.encode())
        ).decode()

        return base64.b64encode(ed).decode(), base64.b64encode(ec).decode(), ki

    def _get_captcha(self):
        """Gen 获取验证码"""
        _, cb64, gen_ki = self._encrypt("{}")
        r = self.session.post(GEN_URL, json={"custom": cb64, "ki": gen_ki})
        g = r.json()
        if g["captcha"]["type"] != "SLIDER":
            raise Exception(f"Gen failed: {g['captcha']}")
        return g

    def _generate_tracks(self, distance: int):
        """生成人类滑动轨迹"""
        tracks = [{"x": 0, "y": 0, "type": "down", "t": 0}]
        cur = 0.0
        mid = distance * random.uniform(0.7, 0.85)
        v = 0.0
        dt = 0.1
        rec_start = int(time.time() * 1000)
        while cur < distance:
            a = random.uniform(1.5, 3.5) if cur < mid else random.uniform(-5.0, -2.0)
            v = max(0.05, v + a * dt)
            cur += v * dt
            tracks.append(
                {
                    "x": int(min(cur, distance)),
                    "y": random.choice([-1, 0, 0, 0, 1]),
                    "type": "move",
                    "t": int(time.time() * 1000) - rec_start,
                }
            )
            time.sleep(random.uniform(0.01, 0.03))
        total = int(time.time() * 1000) - rec_start
        if total < 800:
            total = 800 + random.randint(100, 600)
        tracks.append({"x": distance, "y": 0, "type": "up", "t": total})

        st_dt = datetime.fromtimestamp(rec_start / 1000, timezone.utc)
        st_str = (
            st_dt.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{st_dt.microsecond // 1000:03d}Z"
        )
        et_dt = datetime.fromtimestamp((rec_start + total) / 1000, timezone.utc)
        et_str = (
            et_dt.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{et_dt.microsecond // 1000:03d}Z"
        )
        return tracks, st_str, et_str

    def solve(self, max_retries: int = 3) -> dict:
        """破解滑块验证码，返回 check 响应（含 token）"""
        for _ in range(max_retries):
            g = self._get_captcha()
            cap = g["captcha"]
            bg_b64 = cap["backgroundImage"].split(",")[-1]

            offset = _find_gap(bg_b64)
            tracks, st_str, et_str = self._generate_tracks(offset)

            data_plain = json.dumps(
                {
                    "bgImageWidth": cap.get("backgroundImageWidth", 600),
                    "bgImageHeight": cap.get("backgroundImageHeight", 360),
                    "sliderImageWidth": cap.get("templateImageWidth", 110),
                    "sliderImageHeight": cap.get("templateImageHeight", 360),
                    "startSlidingTime": st_str,
                    "endSlidingTime": et_str,
                    "trackList": tracks,
                },
                separators=(",", ":"),
            )

            db64, cb64, check_ki = self._encrypt(data_plain)
            r = self.session.post(
                CHECK_URL,
                json={
                    "id": g["id"],
                    "data": db64,
                    "custom": cb64,
                    "ki": check_ki,
                },
            )
            result = r.json()
            if result.get("success"):
                return result

        return result


def solve_captcha(username: str = "2025302114221", max_retries: int = 3) -> dict:
    """快捷函数：破解滑块验证码，返回 check 响应（含 data.token）"""
    solver = CaptchaSolver(username=username)
    return solver.solve(max_retries=max_retries)


if __name__ == "__main__":
    result = solve_captcha()
    print(result)
