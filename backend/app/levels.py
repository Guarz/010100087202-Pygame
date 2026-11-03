"""Dữ liệu 12 level, chia 4 chương.

Mỗi level là một trong hai loại:
- "robot": người chơi viết lệnh điều khiển robot trên bản đồ lưới. Mỗi test là một bản đồ.
- "function": người chơi viết một hàm; mỗi test gọi hàm với đầu vào và so sánh kết quả.

Test có `hidden: True` không bao giờ gửi về trình duyệt.
Bản đồ: '#' tường, '.' nền, 'S' xuất phát, 'G' đích, 'C' đồng xu.
"""

ROBOT_API = [
    ("move()", "Đi tới 1 ô theo hướng đang nhìn"),
    ("turn_left()", "Quay trái 90°"),
    ("turn_right()", "Quay phải 90°"),
    ("front_is_clear()", "True nếu ô phía trước không phải tường"),
    ("right_is_clear()", "True nếu ô bên phải không phải tường"),
    ("left_is_clear()", "True nếu ô bên trái không phải tường"),
    ("at_goal()", "True nếu robot đang đứng ở đích"),
    ("on_coin()", "True nếu ô đang đứng có đồng xu"),
    ("pick()", "Nhặt đồng xu ở ô đang đứng"),
]


def corridor(n, coins=()):
    """Hành lang thẳng dài n bước, xu ở các vị trí (1..n-1) trong `coins`."""
    cells = ["C" if i in coins else "." for i in range(1, n)]
    middle = "#S" + "".join(cells) + "G#"
    return ["#" * len(middle), middle, "#" * len(middle)]


CHAPTERS = [
    {"id": 1, "title": "Khu rừng Điều kiện", "topic": "if / elif / else"},
    {"id": 2, "title": "Hang động Vòng lặp", "topic": "for / while"},
    {"id": 3, "title": "Kho báu Dữ liệu", "topic": "list / dict"},
    {"id": 4, "title": "Lâu đài Hàm", "topic": "def / return"},
]

LEVELS = [
    # ---------------- Chương 1: Điều kiện ----------------
    {
        "id": 1, "chapter": 1, "kind": "robot", "scene": "robot",
        "title": "Bước chân đầu tiên",
        "story": "Robot Py tỉnh dậy ở bìa rừng. Hãy giúp nó đi tới cánh cổng phát sáng!",
        "task": "Dùng các lệnh move(), turn_left(), turn_right() để đưa robot tới đích (ô cổng).",
        "starter": "# Robot đang nhìn lên trên (hướng Bắc)\nmove()\n",
        "hints": [
            "Mỗi lệnh move() đi đúng 1 ô. Đếm số ô từ robot lên tới hàng có cổng.",
            "Robot cần đi lên 2 ô, rồi quay phải để nhìn sang cổng.",
            "Lời giải: move() hai lần, turn_right(), rồi move() bốn lần.",
        ],
        "reward": {"id": "boots", "name": "Đôi ủng tập sự", "icon": "shoe-prints"},
        "tests": [
            {"map": ["########", "#....G##", "#.######", "#S######", "########"], "dir": "N"},
        ],
    },
    {
        "id": 2, "chapter": 1, "kind": "function", "scene": "door", "func": "mo_cua",
        "title": "Cánh cửa hai khóa",
        "story": "Cửa đá cổ chỉ mở khi có chìa khóa vàng VÀ đủ năng lượng phép thuật.",
        "task": (
            "Viết hàm mo_cua(chia_khoa, nang_luong) trả về:\n"
            "• \"Mở\" nếu chia_khoa là \"vàng\" và nang_luong >= 50\n"
            "• \"Thiếu năng lượng\" nếu chia_khoa là \"vàng\" nhưng nang_luong < 50\n"
            "• \"Sai chìa khóa\" trong mọi trường hợp còn lại"
        ),
        "starter": "def mo_cua(chia_khoa, nang_luong):\n    # Viết code của bạn ở đây\n    return \"Sai chìa khóa\"\n",
        "hints": [
            "Dùng if / elif / else. Điều kiện đầu tiên cần kiểm tra cả hai thứ cùng lúc với `and`.",
            "So sánh chuỗi bằng ==, ví dụ: chia_khoa == \"vàng\". Đừng nhầm = (gán) với == (so sánh).",
            "if chia_khoa == \"vàng\" and nang_luong >= 50: return \"Mở\"\n"
            "elif chia_khoa == \"vàng\": return \"Thiếu năng lượng\"\nelse: return \"Sai chìa khóa\"",
        ],
        "reward": {"id": "gold_key", "name": "Chìa khóa vàng", "icon": "key"},
        "tests": [
            {"args": ["vàng", 80], "expected": "Mở"},
            {"args": ["vàng", 10], "expected": "Thiếu năng lượng"},
            {"args": ["bạc", 99], "expected": "Sai chìa khóa"},
            {"args": ["vàng", 50], "expected": "Mở", "hidden": True},
            {"args": ["vàng", 49], "expected": "Thiếu năng lượng", "hidden": True},
            {"args": ["đồng", 0], "expected": "Sai chìa khóa", "hidden": True},
        ],
    },
    {
        "id": 3, "chapter": 1, "kind": "robot", "scene": "robot",
        "title": "Ngã rẽ bí ẩn",
        "story": "Sương mù che khuất con đường. Sau 2 bước, lối đi có thể thẳng tiếp hoặc rẽ trái.",
        "task": (
            "Đi 2 bước. Nếu phía trước trống thì đi thẳng 2 bước nữa, "
            "nếu không thì rẽ trái rồi đi 2 bước. Code phải đúng với MỌI bản đồ (có bản đồ ẩn!)."
        ),
        "starter": "move()\nmove()\n# Dùng if front_is_clear(): ... else: ...\n",
        "hints": [
            "front_is_clear() trả về True/False — dùng nó làm điều kiện cho if.",
            "Nhánh else cần turn_left() trước khi move().",
            "if front_is_clear():\n    move(); move()\nelse:\n    turn_left(); move(); move()",
        ],
        "reward": {"id": "lantern", "name": "Đèn lồng xuyên sương", "icon": "lightbulb"},
        "tests": [
            {"map": ["#######", "#S...G#", "#######"], "dir": "E"},
            {"map": ["#######", "###G###", "###.###", "#S..###", "#######"], "dir": "E", "hidden": True},
        ],
    },
    # ---------------- Chương 2: Vòng lặp ----------------
    {
        "id": 4, "chapter": 2, "kind": "robot", "scene": "robot",
        "title": "Hành lang vô tận",
        "story": "Hang động có những hành lang dài bất định. Không ai biết trước cần đi bao nhiêu bước.",
        "task": "Đưa robot tới cuối hành lang. Độ dài hành lang thay đổi ở mỗi bản đồ — hãy dùng vòng lặp while.",
        "starter": "# while điều_kiện:\n#     lệnh\n",
        "hints": [
            "Viết move() nhiều lần sẽ không đúng với hành lang dài hơn ở test ẩn.",
            "Lặp lại move() chừng nào phía trước còn trống: while front_is_clear(): ...",
            "while front_is_clear():\n    move()",
        ],
        "reward": {"id": "torch", "name": "Ngọn đuốc", "icon": "fire"},
        "tests": [
            {"map": corridor(3), "dir": "E"},
            {"map": corridor(7), "dir": "E", "hidden": True},
            {"map": corridor(12), "dir": "E", "hidden": True},
        ],
    },
    {
        "id": 5, "chapter": 2, "kind": "robot", "scene": "robot", "need_coins": True,
        "title": "Mạch vàng trong hang",
        "story": "Dọc hành lang rải rác những đồng xu cổ. Robot phải nhặt HẾT xu rồi mới tới đích.",
        "task": "Đi tới đích và nhặt mọi đồng xu trên đường. Gọi pick() khi không có xu sẽ bị tính là lỗi.",
        "starter": "while not at_goal():\n    # kiểm tra xu rồi đi tiếp\n    move()\n",
        "hints": [
            "Trong mỗi vòng lặp: kiểm tra on_coin() trước, rồi mới move().",
            "Chỉ gọi pick() bên trong if on_coin(): để không nhặt nhầm ô trống.",
            "while not at_goal():\n    if on_coin():\n        pick()\n    move()",
        ],
        "reward": {"id": "coin_bag", "name": "Túi xu cổ", "icon": "sack-dollar"},
        "tests": [
            {"map": corridor(6, coins=(2, 4)), "dir": "E"},
            {"map": corridor(8, coins=(1, 2, 3, 7)), "dir": "E", "hidden": True},
            {"map": corridor(5), "dir": "E", "hidden": True},
        ],
    },
    {
        "id": 6, "chapter": 2, "kind": "function", "scene": "chest", "func": "tong_xu",
        "title": "Rương xu bậc thang",
        "story": "Rương thứ 1 có 1 xu, rương thứ 2 có 2 xu, ... rương thứ n có n xu.",
        "task": "Viết hàm tong_xu(n) trả về tổng số xu trong n rương đầu tiên (1 + 2 + ... + n). Với n = 0 trả về 0.",
        "starter": "def tong_xu(n):\n    tong = 0\n    # dùng vòng lặp for\n    return tong\n",
        "hints": [
            "range(1, n + 1) cho dãy 1, 2, ..., n.",
            "Cộng dồn: tong = tong + i (hoặc tong += i) bên trong vòng for.",
            "for i in range(1, n + 1):\n    tong += i",
        ],
        "reward": {"id": "abacus", "name": "Bàn tính thần", "icon": "calculator"},
        "tests": [
            {"args": [1], "expected": 1},
            {"args": [5], "expected": 15},
            {"args": [10], "expected": 55},
            {"args": [0], "expected": 0, "hidden": True},
            {"args": [100], "expected": 5050, "hidden": True},
            {"args": [37], "expected": 703, "hidden": True},
        ],
    },
    # ---------------- Chương 3: List / dict ----------------
    {
        "id": 7, "chapter": 3, "kind": "function", "scene": "chest", "func": "loc_vat_pham",
        "title": "Sàng lọc kho báu",
        "story": "Túi đồ quá nặng! Chỉ giữ lại những món có giá trị từ ngưỡng trở lên.",
        "task": "Viết hàm loc_vat_pham(gia_tri, nguong) nhận list số nguyên, trả về list mới gồm các số >= nguong, giữ nguyên thứ tự.",
        "starter": "def loc_vat_pham(gia_tri, nguong):\n    ket_qua = []\n    return ket_qua\n",
        "hints": [
            "Duyệt từng phần tử với for x in gia_tri.",
            "Dùng ket_qua.append(x) khi x >= nguong.",
            "Hoặc viết gọn: return [x for x in gia_tri if x >= nguong]",
        ],
        "reward": {"id": "sieve", "name": "Cái sàng ma thuật", "icon": "filter"},
        "tests": [
            {"args": [[10, 60, 30, 90], 50], "expected": [60, 90]},
            {"args": [[5, 5, 5], 5], "expected": [5, 5, 5]},
            {"args": [[1, 2, 3], 10], "expected": []},
            {"args": [[], 1], "expected": [], "hidden": True},
            {"args": [[100, -5, 50, 49, 51], 50], "expected": [100, 50, 51], "hidden": True},
        ],
    },
    {
        "id": 8, "chapter": 3, "kind": "function", "scene": "chest", "func": "dem_vat_pham",
        "title": "Kiểm kê túi đồ",
        "story": "Người thủ kho cần biết mỗi loại vật phẩm có bao nhiêu cái.",
        "task": "Viết hàm dem_vat_pham(tui) nhận list tên vật phẩm, trả về dict {tên: số lượng}.",
        "starter": "def dem_vat_pham(tui):\n    dem = {}\n    return dem\n",
        "hints": [
            "Duyệt từng tên trong tui. Nếu tên chưa có trong dict thì khởi tạo bằng 0.",
            "Kiểm tra khóa bằng `if ten in dem:` hoặc dùng dem.get(ten, 0).",
            "for ten in tui:\n    dem[ten] = dem.get(ten, 0) + 1",
        ],
        "reward": {"id": "ledger", "name": "Sổ kiểm kê", "icon": "book"},
        "tests": [
            {"args": [["kiếm", "khiên", "kiếm"]], "expected": {"kiếm": 2, "khiên": 1}},
            {"args": [["táo"]], "expected": {"táo": 1}},
            {"args": [[]], "expected": {}, "hidden": True},
            {"args": [["a", "b", "a", "c", "b", "a"]], "expected": {"a": 3, "b": 2, "c": 1}, "hidden": True},
        ],
    },
    {
        "id": 9, "chapter": 3, "kind": "function", "scene": "door", "func": "giai_ma",
        "title": "Bản đồ mật mã",
        "story": "Tấm bản đồ ghi bằng mật mã. Bảng giải mã là một dict ánh xạ ký tự → ký tự.",
        "task": (
            "Viết hàm giai_ma(bang_ma, thong_diep): thay mỗi ký tự trong thong_diep bằng bang_ma[ký tự]. "
            "Ký tự không có trong bang_ma thì giữ nguyên. Trả về chuỗi kết quả."
        ),
        "starter": "def giai_ma(bang_ma, thong_diep):\n    ket_qua = \"\"\n    return ket_qua\n",
        "hints": [
            "Duyệt từng ký tự: for kt in thong_diep.",
            "bang_ma.get(kt, kt) trả về ký tự đã giải mã, hoặc chính kt nếu không có trong bảng.",
            "for kt in thong_diep:\n    ket_qua += bang_ma.get(kt, kt)",
        ],
        "reward": {"id": "map", "name": "Bản đồ kho báu", "icon": "map"},
        "tests": [
            {"args": [{"x": "a", "y": "b"}, "xyx"], "expected": "aba"},
            {"args": [{"1": "o", "3": "e"}, "h3ll1 w1rld"], "expected": "hello world"},
            {"args": [{}, "abc"], "expected": "abc", "hidden": True},
            {"args": [{"q": "d", "z": "o", "w": "r"}, "qzzw!"], "expected": "door!", "hidden": True},
        ],
    },
    # ---------------- Chương 4: Hàm & Boss ----------------
    {
        "id": 10, "chapter": 4, "kind": "function", "scene": "boss", "func": "tinh_sat_thuong",
        "title": "Lính gác lâu đài",
        "story": "Lính gác mặc giáp dày. Hãy tính chính xác sát thương mỗi đòn đánh.",
        "task": (
            "Viết hàm tinh_sat_thuong(cong, thu, chi_mang):\n"
            "• Sát thương = cong - thu, nhưng tối thiểu là 1\n"
            "• Nếu chi_mang là True thì nhân đôi sát thương"
        ),
        "starter": "def tinh_sat_thuong(cong, thu, chi_mang):\n    return 0\n",
        "hints": [
            "max(1, cong - thu) đảm bảo sát thương không nhỏ hơn 1.",
            "Lưu vào biến trước, rồi `if chi_mang:` thì nhân đôi biến đó.",
            "st = max(1, cong - thu)\nif chi_mang:\n    st = st * 2\nreturn st",
        ],
        "reward": {"id": "sword", "name": "Kiếm hiệp sĩ", "icon": "khanda"},
        "tests": [
            {"args": [30, 10, False], "expected": 20},
            {"args": [30, 10, True], "expected": 40},
            {"args": [5, 50, False], "expected": 1},
            {"args": [5, 50, True], "expected": 2, "hidden": True},
            {"args": [100, 0, True], "expected": 200, "hidden": True},
        ],
    },
    {
        "id": 11, "chapter": 4, "kind": "robot", "scene": "robot",
        "title": "Mê cung hầm ngục",
        "story": "Hầm ngục là một mê cung ngoằn ngoèo. Mẹo cổ xưa: luôn bám tay phải vào tường!",
        "task": (
            "Đưa robot tới đích trong mọi mê cung. Gợi ý: luật bám tường phải — "
            "nếu bên phải trống thì rẽ phải và đi; nếu không, đi thẳng nếu được; nếu không nữa thì quay trái."
        ),
        "starter": "def buoc_tiep():\n    # quyết định 1 bước theo luật bám tường phải\n    move()\n\nwhile not at_goal():\n    buoc_tiep()\n",
        "hints": [
            "Thứ tự ưu tiên: right_is_clear() → front_is_clear() → còn lại.",
            "Khi rẽ phải phải kèm move() ngay, nếu không robot sẽ quay vòng tại chỗ.",
            "if right_is_clear():\n    turn_right(); move()\nelif front_is_clear():\n    move()\nelse:\n    turn_left()",
        ],
        "reward": {"id": "compass", "name": "La bàn hầm ngục", "icon": "compass"},
        "tests": [
            {"map": ["#########", "#S..#...#", "###.#.#.#", "#...#.#.#", "#.###.#.#", "#.....#G#", "#########"], "dir": "E"},
            {"map": ["#########", "#S#.....#", "#.#.###.#", "#.#...#.#", "#.###.#.#", "#.....#G#", "#########"], "dir": "E", "hidden": True},
            {"map": ["#######", "#S....#", "#####.#", "#G....#", "#######"], "dir": "E", "hidden": True},
        ],
    },
    {
        "id": 12, "chapter": 4, "kind": "function", "scene": "boss", "func": "danh_boss",
        "title": "Rồng Bug cuối cùng",
        "story": "Rồng Bug có nhiều giai đoạn, mỗi giai đoạn có máu (hp) và giáp riêng. Đòn đánh của bạn có lực 30.",
        "task": (
            "Viết hàm danh_boss(cac_giai_doan) nhận list các dict {\"hp\": ..., \"giap\": ...}. "
            "Mỗi đòn gây max(1, 30 - giap) sát thương. Trả về TỔNG số đòn cần để hạ hết các giai đoạn "
            "(mỗi giai đoạn đánh tới khi hp <= 0)."
        ),
        "starter": (
            "def so_don(hp, giap):\n    # số đòn để hạ một giai đoạn\n    return 0\n\n"
            "def danh_boss(cac_giai_doan):\n    tong = 0\n    return tong\n"
        ),
        "hints": [
            "Tách bài toán: viết hàm so_don(hp, giap) cho 1 giai đoạn, rồi cộng dồn trong danh_boss.",
            "Số đòn = làm tròn lên của hp / st. Không cần math: (hp + st - 1) // st, hoặc dùng vòng while trừ dần hp.",
            "def so_don(hp, giap):\n    st = max(1, 30 - giap)\n    return (hp + st - 1) // st\n\n"
            "def danh_boss(ds):\n    return sum(so_don(g[\"hp\"], g[\"giap\"]) for g in ds)",
        ],
        "reward": {"id": "crown", "name": "Vương miện Pythonista", "icon": "crown"},
        "tests": [
            {"args": [[{"hp": 60, "giap": 0}]], "expected": 2},
            {"args": [[{"hp": 100, "giap": 10}, {"hp": 50, "giap": 25}]], "expected": 15},
            {"args": [[]], "expected": 0, "hidden": True},
            {"args": [[{"hp": 1, "giap": 100}]], "expected": 1, "hidden": True},
            {"args": [[{"hp": 95, "giap": 5}, {"hp": 40, "giap": 29}, {"hp": 300, "giap": 0}]], "expected": 54, "hidden": True},
        ],
    },
]

LEVELS_BY_ID = {lv["id"]: lv for lv in LEVELS}
ITEMS = {lv["reward"]["id"]: lv["reward"] for lv in LEVELS}


def public_level(lv):
    """Bản level gửi cho trình duyệt: bỏ test ẩn và gợi ý chưa mở."""
    visible = [t for t in lv["tests"] if not t.get("hidden")]
    data = {k: lv[k] for k in ("id", "chapter", "kind", "scene", "title", "story", "task", "starter", "reward")}
    data["func"] = lv.get("func")
    data["hint_count"] = len(lv["hints"])
    data["test_count"] = len(lv["tests"])
    data["hidden_count"] = len(lv["tests"]) - len(visible)
    if lv["kind"] == "robot":
        data["api"] = ROBOT_API
        data["preview"] = {"map": visible[0]["map"], "dir": visible[0]["dir"]}
    else:
        data["examples"] = [{"args": t["args"], "expected": t["expected"]} for t in visible]
    return data
