"""Nạp biến môi trường từ file .env ở thư mục gốc dự án (nếu có) trước khi các module khác đọc cấu hình.

Biến đã đặt sẵn trong môi trường (ví dụ trên Render) luôn được ưu tiên hơn giá trị trong .env.
"""
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

if _ENV_FILE.exists() and os.environ.get("AUTH_MODE") != "dev":
    for _line in _ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip().strip('"').strip("'"))
