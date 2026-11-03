"""Chạy code người chơi trong một tiến trình con riêng.

Đọc job JSON từ stdin, chạy từng test, in một dòng kết quả có tiền tố `nonce` ra stdout.
Code người chơi đã được judge.py kiểm tra AST trước (cấm import lạ, cấm truy cập thuộc tính `_...`).
File này chỉ dùng thư viện chuẩn và được chạy bằng `python -I -S`.
"""
import copy
import io
import json
import math
import random
import sys

MAX_ACTIONS = 2000
MAX_OUTPUT = 2000
ALLOWED_MODULES = {"math": math, "random": random}


def limit_resources():
    try:
        import resource  # chỉ có trên Linux/macOS (môi trường deploy)
    except ImportError:
        return
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))


class Output:
    def __init__(self):
        self.parts = []
        self.size = 0

    def print(self, *args, sep=" ", end="\n", **_):
        if self.size >= MAX_OUTPUT:
            return
        text = sep.join(str(a) for a in args) + end
        self.parts.append(text[: MAX_OUTPUT - self.size])
        self.size += len(text)

    def text(self):
        out = "".join(self.parts)
        return out + ("\n... (bị cắt bớt)" if self.size > MAX_OUTPUT else "")


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in ALLOWED_MODULES:
        return ALLOWED_MODULES[name]
    raise ImportError(f"Không được phép import '{name}'")


SAFE_NAMES = [
    "abs", "all", "any", "bool", "chr", "dict", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "hash", "int", "isinstance", "iter", "len", "list", "map", "max", "min", "next",
    "ord", "pow", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "zip", "Exception", "ValueError", "TypeError", "IndexError", "KeyError",
    "ZeroDivisionError", "StopIteration", "ArithmeticError", "LookupError", "RuntimeError",
]


def make_builtins(output):
    import builtins
    safe = {name: getattr(builtins, name) for name in SAFE_NAMES}
    safe["print"] = output.print
    safe["__import__"] = safe_import
    safe["__build_class__"] = builtins.__build_class__
    return safe


def error_info(exc):
    line = None
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<code>":
            line = tb.tb_lineno
        tb = tb.tb_next
    return {"type": type(exc).__name__, "msg": str(exc), "line": line}


# ---------------------------------------------------------------- robot

DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
ORDER = "NESW"


class RobotStop(BaseException):
    """Dừng chương trình robot (đâm tường, quá số lệnh...). Không bị `except Exception` bắt."""


class World:
    def __init__(self, test):
        self.grid = [list(row) for row in test["map"]]
        self.dir = test.get("dir", "E")
        self.coins = 0
        for r, row in enumerate(self.grid):
            for c, ch in enumerate(row):
                if ch == "S":
                    self.r, self.c = r, c
                elif ch == "C":
                    self.coins += 1
        self.picked = 0
        self.actions = 0
        self.trace = []
        self.failure = None

    def cell(self, r, c):
        if 0 <= r < len(self.grid) and 0 <= c < len(self.grid[r]):
            return self.grid[r][c]
        return "#"

    def look(self, turn):
        d = ORDER[(ORDER.index(self.dir) + turn) % 4]
        dr, dc = DIRS[d]
        return self.cell(self.r + dr, self.c + dc) != "#"

    def tick(self):
        if self.failure:
            raise RobotStop()
        self.actions += 1
        if self.actions > MAX_ACTIONS:
            self.fail(f"Robot đã chạy quá {MAX_ACTIONS} lệnh — có thể vòng lặp không bao giờ dừng.")

    def fail(self, msg):
        if not self.failure:
            self.failure = msg
        raise RobotStop()

    def api(self):
        def move():
            self.tick()
            if not self.look(0):
                self.trace.append("bump")
                self.fail(f"Robot đâm vào tường ở lần move() thứ {self.trace.count('move') + 1}.")
            dr, dc = DIRS[self.dir]
            self.r, self.c = self.r + dr, self.c + dc
            self.trace.append("move")

        def turn_left():
            self.tick()
            self.dir = ORDER[(ORDER.index(self.dir) - 1) % 4]
            self.trace.append("left")

        def turn_right():
            self.tick()
            self.dir = ORDER[(ORDER.index(self.dir) + 1) % 4]
            self.trace.append("right")

        def front_is_clear():
            self.tick()
            return self.look(0)

        def right_is_clear():
            self.tick()
            return self.look(1)

        def left_is_clear():
            self.tick()
            return self.look(-1)

        def at_goal():
            self.tick()
            return self.cell(self.r, self.c) == "G"

        def on_coin():
            self.tick()
            return self.cell(self.r, self.c) == "C"

        def pick():
            self.tick()
            if self.cell(self.r, self.c) != "C":
                self.trace.append("miss")
                self.fail("Gọi pick() ở ô không có đồng xu.")
            self.grid[self.r][self.c] = "."
            self.picked += 1
            self.trace.append("pick")

        return {f.__name__: f for f in (move, turn_left, turn_right, front_is_clear, right_is_clear,
                                         left_is_clear, at_goal, on_coin, pick)}


def run_robot(job, output):
    code = compile(job["code"], "<code>", "exec")
    results = []
    for test in job["tests"]:
        world = World(test)
        env = {"__builtins__": make_builtins(output), "__name__": "__main__"}
        env.update(world.api())
        error = None
        try:
            exec(code, env)
        except RobotStop:
            pass
        except RecursionError as exc:
            error = {"type": "RecursionError", "msg": str(exc), "line": None}
        except Exception as exc:
            error = error_info(exc)
        at_goal = world.cell(world.r, world.c) == "G"
        reason = world.failure
        if error is None and reason is None:
            if not at_goal:
                reason = "Chương trình đã chạy xong nhưng robot chưa tới đích."
            elif job.get("need_coins") and world.picked < world.coins:
                reason = f"Robot tới đích nhưng mới nhặt {world.picked}/{world.coins} đồng xu."
        results.append({
            "passed": error is None and reason is None,
            "error": error,
            "reason": reason,
            "trace": world.trace[:600],
        })
    return results


# ---------------------------------------------------------------- function

def normalize(value, depth=0):
    """Chuyển kết quả của người chơi về kiểu JSON thuần; kiểu lạ -> TypeError."""
    if depth > 30:
        raise TypeError("cấu trúc lồng nhau quá sâu")
    kind = type(value)
    if value is None or kind in (bool, int, float, str):
        return value
    if kind in (list, tuple):
        return [normalize(v, depth + 1) for v in value]
    if kind is dict:
        out = {}
        for k, v in value.items():
            if type(k) not in (str, int, bool, float) and k is not None:
                raise TypeError("khóa dict có kiểu không hỗ trợ")
            out[k] = normalize(v, depth + 1)
        return out
    raise TypeError(f"kiểu {kind.__name__} không hỗ trợ")


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def run_function(job, output):
    env = {"__builtins__": make_builtins(output), "__name__": "__main__"}
    try:
        exec(compile(job["code"], "<code>", "exec"), env)
    except Exception as exc:
        err = error_info(exc)
        return [{"passed": False, "error": err} for _ in job["tests"]]
    func = env.get(job["func"])
    if not callable(func):
        err = {"type": "MissingFunction", "msg": job["func"], "line": None}
        return [{"passed": False, "error": err} for _ in job["tests"]]
    results = []
    for test in job["tests"]:
        try:
            got = normalize(func(*copy.deepcopy(test["args"])))
        except RecursionError as exc:
            results.append({"passed": False, "error": {"type": "RecursionError", "msg": str(exc), "line": None}})
            continue
        except Exception as exc:
            results.append({"passed": False, "error": error_info(exc)})
            continue
        shown = repr(got)
        results.append({
            "passed": same(test["expected"], got),
            "got": shown if len(shown) <= 300 else shown[:300] + "...",
        })
    return results


def main():
    job = json.loads(sys.stdin.read())
    nonce = job.pop("nonce")
    real_stdout = sys.stdout
    sys.stdout = sys.stderr = io.StringIO()
    sys.setrecursionlimit(400)
    limit_resources()
    output = Output()
    if job["kind"] == "robot":
        results = run_robot(job, output)
    else:
        results = run_function(job, output)
    real_stdout.write(nonce + json.dumps({"results": results, "output": output.text()}) + "\n")
    real_stdout.flush()


if __name__ == "__main__":
    main()
