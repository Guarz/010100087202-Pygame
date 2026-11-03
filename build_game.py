"""Build game Pygame ra WebAssembly bằng pygbag và chép vào frontend/game.

    python build_game.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GAME = ROOT / "game"
OUT = ROOT / "frontend" / "game"

# pygbag đọc file nguồn bằng mã hóa mặc định của hệ điều hành; trên Windows phải ép UTF-8.
env = {**os.environ, "PYTHONUTF8": "1"}
subprocess.run([sys.executable, "-m", "pygbag", "--build", "--ume_block", "0", "--title", "Python Quest", str(GAME)],
               check=True, env=env)

shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(GAME / "build" / "web", OUT)
sys.stdout.reconfigure(encoding="utf-8")
print(f"Đã chép bản build vào {OUT}")
