"""
CAS 密码加密 — 纯 Python 复现，与 encrypt.js 完全等价

encryptPassword(password, salt):
    random64 + password → AES-CBC(key=UTF8(salt), iv=random16, PKCS7) → base64
"""

import base64
import random
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad

_AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def _random_str(length: int) -> str:
    return "".join(random.choice(_AES_CHARS) for _ in range(length))


def encrypt_password(password: str, salt: str) -> str:
    """
    等效于 encrypt.js 的 encryptPassword(password, salt)

    Args:
        password: 明文密码
        salt: pwdEncryptSalt (如 "c3jLJyb3mAKFlsiK")

    Returns:
        base64 密文
    """
    if not salt:
        return password

    # 64 随机字符前缀 + 真实密码
    plaintext = _random_str(64) + password
    key = salt.encode("utf-8")       # 16 bytes
    iv = _random_str(16).encode("utf-8")

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ciphertext).decode()


if __name__ == "__main__":
    # 测试
    salt = "c3jLJyb3mAKFlsiK"
    for pwd in ["test123", "123456", "mypassword"]:
        enc = encrypt_password(pwd, salt)
        print(f"password={pwd} → {enc[:40]}...")
