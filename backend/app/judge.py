"""Code judge: kiểm tra tĩnh, chạy sandbox, và dịch kết quả thành phản hồi tiếng Việt dễ hiểu."""
import ast
import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).with_name("sandbox_runner.py")
TIMEOUT_SECONDS = 5
MAX_CODE_LENGTH = 6000
ALLOWED_IMPORTS = {"math", "random"}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "input", "breakpoint", "help", "exit", "quit", "memoryview", "type", "object", "super", "dir",
    "classmethod", "staticmethod", "property",
}
FORBIDDEN_ATTR_PREFIXES = ("_", "f_", "gi_", "cr_", "ag_", "tb_", "co_")
FORBIDDEN_ATTRS = {"format", "format_map", "mro"}

# Giới hạn số lần chạy judge đồng thời để không làm nghẽn server miễn phí.
_slots = asyncio.Semaphore(int(os.environ.get("JUDGE_CONCURRENCY", "2")))


class CodeRejected(Exception):
    def __init__(self, kind, message, line=None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.line = line


SYNTAX_HINTS = [
    ("expected ':'", "Thiếu dấu hai chấm ':' ở cuối dòng (sau if / elif / else / for / while / def)."),
    ("Maybe you meant '==' or ':='", "Có vẻ bạn dùng '=' trong điều kiện. Để so sánh hãy dùng '=='."),
    ("unterminated string", "Chuỗi chưa được đóng dấu nháy \" hoặc '."),
    ("was never closed", "Có dấu ngoặc mở nhưng chưa đóng."),
    ("unmatched", "Có dấu ngoặc đóng thừa, không khớp với ngoặc mở nào."),
    ("expected an indented block", "Thiếu thụt lề: dòng sau dấu ':' phải lùi vào (4 dấu cách)."),
    ("unexpected indent", "Dòng này bị thụt lề thừa."),
    ("unindent does not match", "Thụt lề không khớp với các dòng phía trên."),
    ("inconsistent use of tabs", "Trộn lẫn Tab và dấu cách khi thụt lề."),
    ("invalid character", "Có ký tự lạ (có thể là dấu nháy cong “ ” hoặc ký tự tiếng Việt ngoài chuỗi)."),
    ("'return' outside function", "Lệnh return chỉ được dùng bên trong hàm (def)."),
    ("cannot assign to", "Vế trái của dấu '=' không phải là tên biến hợp lệ."),
    ("invalid syntax", "Cú pháp không hợp lệ."),
]

RUNTIME_HINTS = {
    "NameError": "Tên chưa được định nghĩa. Kiểm tra chính tả, hoặc bạn quên gán giá trị cho biến trước khi dùng?",
    "UnboundLocalError": "Biến được dùng trước khi gán giá trị trong hàm.",
    "TypeError": "Sai kiểu dữ liệu (ví dụ cộng số với chuỗi, gọi hàm sai số tham số).",
    "IndexError": "Truy cập vị trí vượt quá độ dài của list/chuỗi.",
    "KeyError": "Khóa không tồn tại trong dict. Dùng `in` hoặc .get() để kiểm tra trước.",
    "ZeroDivisionError": "Phép chia cho 0.",
    "AttributeError": "Kiểu dữ liệu này không có phương thức/thuộc tính đó.",
    "ValueError": "Giá trị không hợp lệ cho thao tác này.",
    "RecursionError": "Đệ quy quá sâu — hàm gọi chính nó mà không có điểm dừng?",
    "ImportError": "Chỉ được import math hoặc random.",
    "MissingFunction": "Không tìm thấy hàm cần viết. Hãy giữ đúng tên hàm như đề bài.",
}


def check_code(code):
    """Phân tích cú pháp và chặn các cấu trúc nguy hiểm. Ném CodeRejected nếu không hợp lệ."""
    if len(code) > MAX_CODE_LENGTH:
        raise CodeRejected("forbidden", f"Code quá dài (tối đa {MAX_CODE_LENGTH} ký tự).")
    try:
        tree = ast.parse(code, filename="<code>")
    except SyntaxError as exc:
        raw = exc.msg or ""
        hint = next((vi for en, vi in SYNTAX_HINTS if en in raw), "Lỗi cú pháp.")
        raise CodeRejected("syntax", f"{hint} (Python: {raw})", exc.lineno) from None

    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Import):
            bad = [a.name for a in node.names if a.name not in ALLOWED_IMPORTS]
            if bad:
                raise CodeRejected("forbidden", f"Không được phép import {', '.join(bad)}. Chỉ dùng math hoặc random.", line)
        elif isinstance(node, ast.ImportFrom):
            if node.module not in ALLOWED_IMPORTS or node.level:
                raise CodeRejected("forbidden", "Chỉ được import từ math hoặc random.", line)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith(FORBIDDEN_ATTR_PREFIXES) or node.attr in FORBIDDEN_ATTRS:
                raise CodeRejected("forbidden", f"Không được truy cập thuộc tính '{node.attr}'.", line)
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES or (node.id.startswith("__") and node.id != "__name__"):
                raise CodeRejected("forbidden", f"Không được dùng '{node.id}' trong game.", line)
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            raise CodeRejected("forbidden", "Game không hỗ trợ async/await.", line)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                raise CodeRejected("forbidden", "Tên hàm/lớp không được bắt đầu bằng dấu '_'.", line)
    return tree


def _run_process(job):
    nonce = secrets.token_hex(16)
    payload = json.dumps({**job, "nonce": nonce})
    env = {"PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", str(RUNNER)],
                input=payload.encode("utf-8"), capture_output=True, timeout=TIMEOUT_SECONDS, cwd=tmp, env=env,
            )
        except subprocess.TimeoutExpired:
            return None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith(nonce):
            return json.loads(line[len(nonce):])
    # Tiến trình chết trước khi in kết quả (vượt giới hạn bộ nhớ/CPU).
    return {"crashed": True}


def describe_error(err):
    kind = err["type"]
    hint = RUNTIME_HINTS.get(kind, "Chương trình gặp lỗi khi chạy.")
    where = f"Dòng {err['line']}: " if err.get("line") else ""
    detail = f" (Python: {kind}: {err['msg']})" if kind != "MissingFunction" else f" (cần hàm {err['msg']})"
    return f"{where}{hint}{detail}"


def short(value, limit=160):
    text = repr(value) if not isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


async def judge(level, code, include_hidden):
    """Chấm code cho một level. Trả về dict kết quả dùng trực tiếp cho API."""
    tests = [t for t in level["tests"] if include_hidden or not t.get("hidden")]
    base = {"passed": 0, "total": len(tests), "tests": [], "output": "", "animation": None}

    try:
        check_code(code)
    except CodeRejected as exc:
        where = f"Dòng {exc.line}: " if exc.line else ""
        return {**base, "status": "error", "error_type": exc.kind, "summary": where + exc.message, "line": exc.line}

    job = {"kind": level["kind"], "code": code, "tests": tests}
    if level["kind"] == "robot":
        job["need_coins"] = bool(level.get("need_coins"))
    else:
        job["func"] = level["func"]

    async with _slots:
        raw = await asyncio.to_thread(_run_process, job)

    if raw is None:
        return {**base, "status": "error", "error_type": "timeout",
                "summary": f"Code chạy quá {TIMEOUT_SECONDS} giây — có thể có vòng lặp vô hạn (while không bao giờ sai)."}
    if raw.get("crashed"):
        return {**base, "status": "error", "error_type": "runtime",
                "summary": "Chương trình dùng quá nhiều bộ nhớ hoặc CPU và bị dừng."}

    report, first_error, first_line = [], None, None
    visible_no = hidden_no = 0
    for test, res in zip(tests, raw["results"]):
        hidden = bool(test.get("hidden"))
        if hidden:
            hidden_no += 1
            name = f"Test ẩn {hidden_no}"
        else:
            visible_no += 1
            name = f"Test {visible_no}"
        item = {"name": name, "hidden": hidden, "passed": res["passed"]}
        if res.get("error"):
            message = describe_error(res["error"])
            first_error = first_error or message
            first_line = first_line or res["error"].get("line")
        elif level["kind"] == "robot":
            message = res.get("reason") or "Robot tới đích!"
        else:
            message = "Đúng!" if res["passed"] else "Kết quả chưa đúng."
        if hidden and not res["passed"] and not res.get("error"):
            message = "Sai ở một trường hợp đặc biệt. Hãy nghĩ tới giá trị biên (0, rỗng, bằng ngưỡng...)."
            if level["kind"] == "robot":
                message = "Robot thất bại trên một bản đồ khác. Code của bạn có đang 'học thuộc' bản đồ mẫu không?"
        item["message"] = message
        if not hidden and level["kind"] == "function":
            item["input"] = ", ".join(short(a) for a in test["args"])
            item["expected"] = short(test["expected"])
            item["got"] = res.get("got")
        report.append(item)

    passed = sum(1 for r in report if r["passed"])
    if passed == len(report):
        status, error_type, summary = "passed", "ok", "Tuyệt vời! Tất cả test đều đúng."
    elif first_error:
        status, error_type, summary = "failed", "runtime", first_error
    else:
        status, error_type = "failed", "logic"
        summary = (f"Code chạy được nhưng mới đúng {passed}/{len(report)} test — đây là lỗi tư duy (logic), "
                   "không phải lỗi cú pháp. Xem test sai bên dưới.")

    if level["kind"] == "robot":
        first = 0  # test hiện đầu tiên luôn ở đầu danh sách
        animation = {"type": "robot", "map": tests[first]["map"], "dir": tests[first]["dir"],
                     "trace": raw["results"][first]["trace"], "passed": raw["results"][first]["passed"]}
    else:
        animation = {"type": "scene", "scene": level["scene"], "results": [r["passed"] for r in report]}

    return {**base, "status": status, "error_type": error_type, "summary": summary, "line": first_line,
            "passed": passed, "tests": report, "output": raw.get("output", ""), "animation": animation}
