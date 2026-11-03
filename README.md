# Python Quest — Game phiêu lưu học Python có code judge

Người chơi điều khiển robot và giải câu đố bằng code Python thật. Có 12 màn chia làm 4 chương: điều kiện → vòng lặp → list/dict → hàm & boss.
Code được chấm trên server với test hiện và test ẩn. Hệ thống phản hồi lỗi bằng tiếng Việt, có gợi ý từng bước, túi đồ, bảng xếp hạng và trang quản trị.

## Kiến trúc

```
Trình duyệt
├── Trang web (HTML/JS): đăng nhập Supabase, bản đồ, editor CodeMirror, BXH, admin
│     └── iframe: game Pygame build bằng pygbag (WebAssembly) — vẽ bản đồ, diễn hoạt kết quả
│           ▲ trang web gửi lệnh cho game qua localStorage ("pq_cmd")
└── gọi /api/* ─► FastAPI (backend/app)
                    ├── auth.py    xác minh token Supabase, phân quyền player/admin, khóa tài khoản
                    ├── judge.py   kiểm tra AST + chạy sandbox_runner.py trong tiến trình con có giới hạn
                    ├── levels.py  12 màn, test ẩn chỉ nằm trên server
                    └── db.py      PostgreSQL (Supabase) / SQLite khi chạy local
```

**Vì sao chấm trên server?** Nếu chấm ở trình duyệt, người chơi có thể sửa điểm hoặc đọc test ẩn. Ở đây trình duyệt chỉ nhận về kết quả và "trace" để game diễn hoạt.
Riêng test ẩn của màn robot thì không gửi cả bản đồ.

**Sandbox.** Code của người chơi phải qua các lớp bảo vệ sau:
1. Kiểm tra AST: chỉ cho `import math`/`random`; cấm `open`, `eval`, `exec`, `type`... và mọi thuộc tính bắt đầu bằng `_`, `f_`, `gi_`...
2. Chạy trong tiến trình con riêng (`python -I -S`), builtins bị thu hẹp, biến môi trường bị xóa.
3. Bị dừng sau 5 giây. Robot bị giới hạn 2000 lệnh. Trên Linux còn có giới hạn CPU 3s, RAM 256MB và số file mở.
4. Kết quả được đọc theo một mã `nonce` ngẫu nhiên, nên `print` của người chơi không giả mạo được kết quả.

Mức này đủ cho đồ án/lớp học. Nếu cần chặt chẽ ở mức production, nên chạy judge trong container riêng (Docker/gVisor, Judge0...).

## Chạy local

Yêu cầu Python 3.11 trở lên.

```bash
python -m venv .venv
.venv\Scripts\pip install -r backend/requirements.txt pygame-ce pygbag pytest
```

```powershell
.\run_dev.cmd
```

Trong PowerShell phải có `.\` ở đầu (CMD thì gõ `run_dev.cmd` là được). Muốn chạy local nhưng dùng Supabase thật theo file `.env`, chạy `.\run_supabase.cmd` rồi mở http://localhost:8001.

Sau đó mở http://localhost:8000. Ở chế độ dev, chỉ cần nhập email là đăng nhập được, không cần mật khẩu. Email `admin@local.dev` có quyền admin.

- Chạy test backend (lời giải mẫu 12 màn, các ca tấn công sandbox, API): `cd backend` rồi `..\.venv\Scripts\python -m pytest -q tests`
- Chạy thử game trên desktop: `.venv\Scripts\python game\main.py` (bấm phím 1–4 để đổi cảnh demo)
- Sau khi sửa `game/main.py`, build lại bản web: `.venv\Scripts\python build_game.py` (kết quả nằm ở `frontend/game/`, nhớ commit thư mục này)

Lần đầu mở một màn chơi, game có thể mất 10–20 giây để tải runtime Python WebAssembly từ CDN của pygbag. Các lần sau trình duyệt dùng cache nên nhanh hơn.

## Deploy (Supabase + Render)

### 1. Supabase
1. Tạo project mới.
2. Vào **Project Settings → API** và chép **Project URL** cùng khóa **anon / publishable**.
3. Bấm **Connect**, chọn **Session pooler** (hỗ trợ IPv4, Render cần cái này) và chép connection string. Thay `[YOUR-PASSWORD]` bằng mật khẩu database.
4. Vào **Authentication → URL Configuration**, đặt **Site URL** là URL Render (ví dụ `https://python-quest.onrender.com`), rồi thêm URL đó vào Redirect URLs.
5. (Tùy chọn) Vào **Authentication → Providers → Email** để bật hoặc tắt "Confirm email".

Không cần tạo bảng bằng tay. Backend tự tạo các bảng `pq_*` khi khởi động và tự bật Row Level Security, để anon key công khai không đọc được dữ liệu qua Data API.

### 2. Render
1. Push repo lên GitHub.
2. Vào Render → **New → Blueprint**, chọn repo. Render sẽ đọc file `render.yaml`.
3. Điền các biến môi trường:

| Biến | Giá trị |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_ANON_KEY` | khóa anon / publishable |
| `DATABASE_URL` | connection string Session pooler |
| `ADMIN_EMAILS` | email của bạn (cách nhau bằng dấu phẩy); tài khoản này tự thành admin khi đăng nhập |

Không bao giờ đặt `AUTH_MODE=dev` trên server thật. Gói free của Render sẽ "ngủ" sau 15 phút không có truy cập, nên lần truy cập đầu tiên sau đó sẽ chậm khoảng 30–60 giây.

## Tính năng theo yêu cầu đề bài

| Yêu cầu | Ở đâu |
|---|---|
| Mỗi màn là một nhiệm vụ lập trình (điều kiện, vòng lặp, list/dict, hàm/boss) | `backend/app/levels.py` |
| Trình soạn code trên web | `frontend/play.html` (CodeMirror, Tab = 4 dấu cách, Ctrl+Enter) |
| Test hiện/ẩn, chấm điểm | `judge.py`; điểm = % test đúng − 10 × số gợi ý đã mở |
| Phân biệt lỗi cú pháp / lỗi chạy / lỗi tư duy | `judge.py` (`SYNTAX_HINTS`, `RUNTIME_HINTS`, có số dòng, tô đỏ dòng lỗi trong editor) |
| Gợi ý từng bước | 3 gợi ý/màn, mở dần qua `POST /api/levels/{id}/hint` |
| Hệ thống level, mở khóa tuần tự | `is_unlocked` trong `main.py` |
| Inventory | Mỗi màn thưởng 1 vật phẩm, xem ở `map.html` |
| Lưu tiến độ | Bảng `pq_progress` (điểm cao nhất, số lần nộp, code gần nhất) |
| Leaderboard | `leaderboard.html`, `GET /api/leaderboard` |
| Đăng nhập & phân quyền, quản lý user | Supabase Auth; `admin.html`: đổi vai trò, khóa tài khoản |
| Analytics | Bảng `pq_events` + `pq_submissions`; admin xem tỉ lệ đạt từng màn, loại lỗi, người chơi theo ngày |
| Tài liệu API | `/api/docs` (Swagger) |
