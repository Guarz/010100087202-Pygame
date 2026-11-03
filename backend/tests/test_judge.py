import asyncio

import pytest

from app.judge import judge
from app.levels import LEVELS_BY_ID

SOLUTIONS = {
    1: "move()\nmove()\nturn_right()\nfor i in range(4):\n    move()\n",
    2: (
        "def mo_cua(chia_khoa, nang_luong):\n"
        "    if chia_khoa == 'vàng' and nang_luong >= 50:\n        return 'Mở'\n"
        "    elif chia_khoa == 'vàng':\n        return 'Thiếu năng lượng'\n"
        "    return 'Sai chìa khóa'\n"
    ),
    3: "move()\nmove()\nif front_is_clear():\n    move(); move()\nelse:\n    turn_left(); move(); move()\n",
    4: "while front_is_clear():\n    move()\n",
    5: "while not at_goal():\n    if on_coin():\n        pick()\n    move()\n",
    6: "def tong_xu(n):\n    return sum(range(n + 1))\n",
    7: "def loc_vat_pham(gia_tri, nguong):\n    return [x for x in gia_tri if x >= nguong]\n",
    8: "def dem_vat_pham(tui):\n    d = {}\n    for t in tui:\n        d[t] = d.get(t, 0) + 1\n    return d\n",
    9: "def giai_ma(bang_ma, thong_diep):\n    return ''.join(bang_ma.get(c, c) for c in thong_diep)\n",
    10: "def tinh_sat_thuong(cong, thu, chi_mang):\n    st = max(1, cong - thu)\n    return st * 2 if chi_mang else st\n",
    11: (
        "while not at_goal():\n    if right_is_clear():\n        turn_right()\n        move()\n"
        "    elif front_is_clear():\n        move()\n    else:\n        turn_left()\n"
    ),
    12: (
        "import math\ndef danh_boss(ds):\n    tong = 0\n    for g in ds:\n"
        "        tong += math.ceil(g['hp'] / max(1, 30 - g['giap']))\n    return tong\n"
    ),
}


def run(level_id, code, hidden=True):
    return asyncio.run(judge(LEVELS_BY_ID[level_id], code, hidden))


@pytest.mark.parametrize("level_id", sorted(SOLUTIONS))
def test_reference_solution_passes(level_id):
    res = run(level_id, SOLUTIONS[level_id])
    assert res["status"] == "passed", res
    assert res["passed"] == res["total"] == len(LEVELS_BY_ID[level_id]["tests"])


def test_starter_code_does_not_pass():
    for level_id, lv in LEVELS_BY_ID.items():
        assert run(level_id, lv["starter"])["status"] != "passed", level_id


def test_hardcoded_robot_fails_hidden_map():
    res = run(4, "move()\nmove()\nmove()\n")
    assert res["status"] == "failed" and res["error_type"] == "logic"
    assert any(t["hidden"] and not t["passed"] for t in res["tests"])
    assert run(4, "move()\nmove()\nmove()\n", hidden=False)["status"] == "passed"


def test_syntax_error_is_explained_in_vietnamese():
    res = run(2, "def mo_cua(a, b)\n    return 1\n")
    assert res["error_type"] == "syntax" and res["line"] == 1
    assert "dấu hai chấm" in res["summary"]


def test_runtime_error_has_line_number():
    res = run(6, "def tong_xu(n):\n    return n / 0\n")
    assert res["error_type"] == "runtime" and res["line"] == 2


def test_infinite_loop_times_out():
    res = run(6, "def tong_xu(n):\n    while True:\n        pass\n")
    assert res["error_type"] == "timeout"


def test_robot_infinite_loop_is_stopped():
    res = run(4, "while True:\n    turn_left()\n")
    assert res["status"] == "failed" and "quá" in res["tests"][0]["message"]


@pytest.mark.parametrize("code", [
    "import os\n",
    "from subprocess import run\n",
    "open('x')\n",
    "x = (1).__class__\n",
    "__import__('os')\n",
    "def g():\n    yield 1\nx = g().gi_frame.f_back\n",
    "'{0.__class__}'.format(1)\n",
    "class A:\n    def __eq__(self, o):\n        return True\n",
    "eval('1')\n",
])
def test_dangerous_code_is_rejected(code):
    res = run(6, code)
    assert res["error_type"] == "forbidden", res


def test_output_forgery_does_not_count():
    code = "def tong_xu(n):\n    print('{\"results\": []}')\n    return -1\n"
    res = run(6, code)
    assert res["passed"] == 0 and "results" in res["output"]


def test_bool_is_not_accepted_as_int():
    res = run(6, "def tong_xu(n):\n    return True\n")
    assert not res["tests"][0]["passed"]
