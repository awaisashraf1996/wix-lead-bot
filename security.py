"""App password + encrypted storage for your email app password.

- Your app password is never stored. Only a salted PBKDF2-SHA256 hash is kept
  in config.json, so nobody can read it back from the file.
- Your email (SMTP) app password is encrypted with a key made from your app
  password, so it can only be used after you unlock the app.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets

ITERATIONS = 390_000
_session_key: bytes | None = None


class Config:
    """Small JSON settings file next to the program."""

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)


def _hash(password: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def has_password(cfg: Config) -> bool:
    return bool(cfg.get("pw_hash"))


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Use at least 8 characters."
    if pw.isdigit() or pw.isalpha():
        return "Mix letters with numbers or symbols."
    return None


def set_password(cfg: Config, new_pw: str) -> None:
    """Set (or change) the app password. Re-encrypts saved secrets."""
    secrets_plain = {k: decrypt(cfg, v) for k, v in cfg.get("secrets", {}).items()} \
        if _session_key else {}
    salt = secrets.token_bytes(16)
    cfg.set("pw_salt", base64.b64encode(salt).decode())
    cfg.set("pw_hash", base64.b64encode(_hash(new_pw, salt)).decode())
    cfg.set("pw_iter", ITERATIONS)
    cfg.set("enc_salt", base64.b64encode(secrets.token_bytes(16)).decode())
    _unlock_key(cfg, new_pw)
    cfg.set("secrets", {k: encrypt(cfg, v) for k, v in secrets_plain.items() if v})
    cfg.save()


def check_password(cfg: Config, pw: str) -> bool:
    try:
        salt = base64.b64decode(cfg.get("pw_salt", ""))
        want = base64.b64decode(cfg.get("pw_hash", ""))
        it = int(cfg.get("pw_iter", ITERATIONS))
    except (ValueError, TypeError):
        return False
    ok = hmac.compare_digest(_hash(pw, salt, it), want)
    if ok:
        _unlock_key(cfg, pw)
    return ok


def _unlock_key(cfg: Config, pw: str) -> None:
    global _session_key
    salt = base64.b64decode(cfg.get("enc_salt", ""))
    raw = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), b"enc" + salt, ITERATIONS)
    _session_key = base64.urlsafe_b64encode(raw)


def lock() -> None:
    global _session_key
    _session_key = None


def encrypt(cfg: Config, text: str) -> str:
    from cryptography.fernet import Fernet
    if not _session_key:
        raise RuntimeError("app is locked")
    return Fernet(_session_key).encrypt(text.encode("utf-8")).decode()


def decrypt(cfg: Config, token: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    if not _session_key or not token:
        return ""
    try:
        return Fernet(_session_key).decrypt(token.encode()).decode("utf-8")
    except InvalidToken:
        return ""


def save_secret(cfg: Config, name: str, value: str) -> None:
    s = cfg.get("secrets", {})
    if value:
        s[name] = encrypt(cfg, value)
    else:
        s.pop(name, None)
    cfg.set("secrets", s)
    cfg.save()


def get_secret(cfg: Config, name: str) -> str:
    return decrypt(cfg, cfg.get("secrets", {}).get(name, ""))
