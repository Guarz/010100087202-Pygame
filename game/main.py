"""Python Quest — phần hiển thị game viết bằng Pygame, build ra web bằng pygbag.

Game không tự chấm code: trang web (frontend) gửi lệnh qua localStorage key "pq_cmd",
game vẽ lại bản đồ / cảnh và diễn hoạt kết quả chấm từ server.
Chạy trên desktop (python main.py) sẽ dùng lệnh demo, bấm phím 1-4 để đổi cảnh.
"""
import asyncio
import json
import math
import random
import sys

import pygame

WEB = sys.platform == "emscripten"
if WEB:
    import platform as web  # module đặc biệt của pygbag, truy cập `window` của trình duyệt

W, H = 640, 360  # 16:9, khớp tỉ lệ canvas mặc định của pygbag
# Font mặc định của pygame (freesansbold) thiếu nhiều chữ tiếng Việt (Ư, Ạ, Ồ...):
# chữ hiển thị trong game chỉ dùng các ký tự Latin-1 + Đ, phần chữ dài nằm ở trang web.
DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
ANGLE = {"N": -90, "E": 0, "S": 90, "W": 180}

BG = (20, 24, 38)
FLOOR = (46, 54, 78)
FLOOR_ALT = (52, 61, 88)
WALL = (88, 70, 120)
WALL_TOP = (120, 98, 160)
GOLD = (255, 204, 77)
GREEN = (88, 214, 141)
RED = (239, 99, 99)
CYAN = (94, 214, 255)
WHITE = (236, 240, 255)
MUTED = (150, 160, 190)

DEMO = [
    {"type": "robot", "map": ["#########", "#S..#...#", "###.#.#.#", "#...#.#.#", "#.###.#.#", "#.....#G#", "#########"],
     "dir": "E", "passed": True,
     "trace": ["move", "move", "right", "move", "move", "right", "move", "move", "left", "move", "move", "left",
               "move", "move", "move", "move", "left", "move", "move", "move", "move", "right", "move", "move",
               "right", "move", "move", "move", "move"]},
    {"type": "robot", "map": ["##########", "#S.C.CC.G#", "##########"], "dir": "E", "passed": False,
     "trace": ["move", "move", "pick", "move", "move", "pick", "move", "miss"]},
    {"type": "scene", "scene": "boss", "results": [True, True, False, True, True]},
    {"type": "scene", "scene": "door", "results": [True, True, True, True]},
]


def ease(t):
    return t * t * (3 - 2 * t)


class Particles:
    def __init__(self):
        self.items = []

    def burst(self, x, y, color, n=18, speed=140):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            v = random.uniform(speed * 0.3, speed)
            self.items.append([x, y, math.cos(a) * v, math.sin(a) * v, random.uniform(0.4, 0.9), color])

    def update(self, dt):
        for p in self.items:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 220 * dt
            p[4] -= dt
        self.items = [p for p in self.items if p[4] > 0]

    def draw(self, surf):
        for x, y, _, _, life, color in self.items:
            pygame.draw.circle(surf, color, (int(x), int(y)), max(1, int(4 * life)))


class Banner:
    def __init__(self):
        self.text, self.color, self.t = "", WHITE, 0

    def show(self, text, color):
        self.text, self.color, self.t = text, color, 0.0

    def draw(self, surf, fonts, dt):
        if not self.text:
            return
        self.t += dt
        k = min(1, self.t / 0.35)
        h = int(48 * ease(k))
        box = pygame.Rect(0, 30 - h // 2, W, h)
        overlay = pygame.Surface(box.size, pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 200))
        surf.blit(overlay, box)
        if k >= 1:
            img = fonts["big"].render(self.text, True, self.color)
            surf.blit(img, img.get_rect(center=(W // 2, 30)))


# ------------------------------------------------------------------ robot

class RobotScene:
    def __init__(self, cmd, fx, banner):
        self.grid = [list(row) for row in cmd["map"]]
        self.rows = len(self.grid)
        self.cols = max(len(r) for r in self.grid)
        self.dir = cmd.get("dir", "E")
        for r, row in enumerate(self.grid):
            for c, ch in enumerate(row):
                if ch == "S":
                    self.pos = [float(r), float(c)]
                    self.grid[r][c] = "."
        self.angle = ANGLE[self.dir]
        self.trace = list(cmd.get("trace") or [])
        self.passed = cmd.get("passed")
        self.fx, self.banner = fx, banner
        self.tile = int(min((W - 40) / self.cols, (H - 60) / self.rows, 56))
        self.ox = (W - self.tile * self.cols) // 2
        self.oy = (H - self.tile * self.rows) // 2 + 10
        self.step_time = max(0.06, min(0.28, 7.0 / max(1, len(self.trace))))
        self.i, self.t = 0, 0.0
        self.start = None
        self.shake = 0.0
        self.done = not self.trace
        self.clock = 0.0

    def center(self, r, c):
        return self.ox + c * self.tile + self.tile / 2, self.oy + r * self.tile + self.tile / 2

    def begin_step(self):
        self.start = (self.pos[:], self.angle)

    def update(self, dt):
        self.clock += dt
        self.shake = max(0, self.shake - dt)
        if self.done:
            return
        if self.start is None:
            self.begin_step()
        action = self.trace[self.i]
        self.t += dt / self.step_time
        k = ease(min(1, self.t))
        (r0, c0), a0 = self.start
        dr, dc = DIRS[self.dir]
        if action == "move":
            self.pos = [r0 + dr * k, c0 + dc * k]
        elif action == "bump":
            bounce = math.sin(k * math.pi) * 0.3
            self.pos = [r0 + dr * bounce, c0 + dc * bounce]
        elif action in ("left", "right"):
            self.angle = a0 + (-90 if action == "left" else 90) * k
        if self.t < 1:
            return
        # kết thúc một bước
        if action == "move":
            self.pos = [round(r0 + dr), round(c0 + dc)]
        elif action == "left":
            self.dir = "NESW"["NESW".index(self.dir) - 1]
        elif action == "right":
            self.dir = "NESW"[("NESW".index(self.dir) + 1) % 4]
        x, y = self.center(*self.pos)
        if action == "pick":
            self.grid[int(self.pos[0])][int(self.pos[1])] = "."
            self.fx.burst(x, y, GOLD)
        elif action in ("bump", "miss"):
            self.shake = 0.35
            self.fx.burst(x, y, RED, 10)
        self.i += 1
        self.t = 0
        self.start = None
        if self.i >= len(self.trace):
            self.finish()

    def finish(self):
        self.done = True
        x, y = self.center(*self.pos)
        if self.passed:
            self.fx.burst(x, y, GREEN, 40, 220)
            self.banner.show("THÀNH CÔNG!", GREEN)
        elif self.passed is False:
            self.banner.show("KHÔNG THÀNH CÔNG", RED)

    def draw(self, surf, fonts):
        sx = random.uniform(-4, 4) if self.shake else 0
        t = self.tile
        for r in range(self.rows):
            for c in range(self.cols):
                ch = self.grid[r][c] if c < len(self.grid[r]) else "#"
                rect = pygame.Rect(self.ox + c * t + sx, self.oy + r * t, t, t)
                if ch == "#":
                    pygame.draw.rect(surf, WALL, rect)
                    pygame.draw.rect(surf, WALL_TOP, rect.inflate(-4, -4).move(0, -2), border_radius=4)
                    continue
                pygame.draw.rect(surf, FLOOR if (r + c) % 2 else FLOOR_ALT, rect)
                cx, cy = rect.center
                if ch == "G":
                    glow = 0.5 + 0.5 * math.sin(self.clock * 4)
                    pygame.draw.circle(surf, (60, 120, 200), (cx, cy), int(t * 0.42))
                    pygame.draw.circle(surf, CYAN, (cx, cy), int(t * (0.26 + 0.08 * glow)), 3)
                    pygame.draw.circle(surf, WHITE, (cx, cy), int(t * 0.1))
                elif ch == "C":
                    bob = math.sin(self.clock * 5 + c) * 2
                    pygame.draw.circle(surf, (190, 140, 30), (cx, cy + bob), int(t * 0.22))
                    pygame.draw.circle(surf, GOLD, (cx, cy + bob), int(t * 0.17))
        self.draw_robot(surf, sx)

    def draw_robot(self, surf, sx):
        t = self.tile
        x, y = self.center(*self.pos)
        x += sx
        body = pygame.Rect(0, 0, t * 0.62, t * 0.62)
        body.center = (x, y)
        pygame.draw.line(surf, MUTED, (x, body.top), (x, body.top - t * 0.15), 2)
        pygame.draw.circle(surf, RED if self.shake else GOLD, (int(x), int(body.top - t * 0.17)), max(2, t // 14))
        pygame.draw.rect(surf, (200, 210, 235), body, border_radius=int(t * 0.15))
        pygame.draw.rect(surf, (120, 130, 170), body, 2, border_radius=int(t * 0.15))
        a = math.radians(self.angle)
        ex, ey = x + math.cos(a) * t * 0.16, y + math.sin(a) * t * 0.16
        pygame.draw.circle(surf, (30, 36, 60), (int(ex), int(ey)), max(3, int(t * 0.12)))
        pygame.draw.circle(surf, CYAN, (int(ex + math.cos(a) * 2), int(ey + math.sin(a) * 2)), max(2, int(t * 0.05)))


# ------------------------------------------------------------------ scenes cho level dạng hàm

class TestScene:
    """Cửa / rương / boss: mỗi test đúng là một khóa mở, viên ngọc sáng, hoặc một đòn đánh trúng boss."""

    def __init__(self, cmd, fx, banner):
        self.kind = cmd.get("scene", "door")
        self.results = cmd.get("results")
        self.n = len(self.results) if self.results else 5
        self.revealed = 0
        self.timer = 0.6
        self.fx, self.banner = fx, banner
        self.clock = 0.0
        self.hp = self.n
        self.shown_hp = float(self.n)
        self.flash = 0.0
        self.open = 0.0
        self.shots = []
        self.done = self.results is None

    @property
    def success(self):
        return bool(self.results) and all(self.results)

    def update(self, dt):
        self.clock += dt
        self.flash = max(0, self.flash - dt)
        self.shown_hp += (self.hp - self.shown_hp) * min(1, dt * 6)
        for s in self.shots:
            s[0] += dt * 2.2
        for s in [s for s in self.shots if s[0] >= 1]:
            self.fx.burst(470, 190, GOLD, 22, 180)
        self.shots = [s for s in self.shots if s[0] < 1]
        if self.done:
            if self.success:
                self.open = min(1, self.open + dt * 0.8)
            return
        self.timer -= dt
        if self.timer > 0:
            return
        ok = self.results[self.revealed]
        x, y = self.slot_pos(self.revealed)
        if self.kind == "boss":
            if ok:
                self.hp -= 1
                self.shots.append([0.0])
            else:
                self.flash = 0.4
        else:
            self.fx.burst(x, y, GREEN if ok else RED, 14)
        self.revealed += 1
        self.timer = 0.45
        if self.revealed >= self.n:
            self.done = True
            if self.success:
                self.banner.show("BOSS ĐÃ THUA!" if self.kind == "boss" else "THÀNH CÔNG!", GREEN)
            else:
                passed = sum(self.results)
                self.banner.show(f"ĐÚNG {passed}/{self.n} TEST", GOLD if passed else RED)

    def slot_pos(self, i):
        gap = min(60, 440 // max(1, self.n))
        x0 = W // 2 - gap * (self.n - 1) / 2
        return x0 + gap * i, 318

    def draw_slots(self, surf, fonts):
        for i in range(self.n):
            x, y = self.slot_pos(i)
            if i < self.revealed:
                ok = self.results[i]
                pygame.draw.circle(surf, GREEN if ok else RED, (int(x), y), 16)
                if ok:
                    pygame.draw.lines(surf, BG, False, [(x - 7, y), (x - 2, y + 6), (x + 8, y - 6)], 4)
                else:
                    pygame.draw.line(surf, BG, (x - 6, y - 6), (x + 6, y + 6), 4)
                    pygame.draw.line(surf, BG, (x - 6, y + 6), (x + 6, y - 6), 4)
            else:
                pygame.draw.circle(surf, (70, 78, 105), (int(x), y), 16)
                pygame.draw.circle(surf, MUTED, (int(x), y), 16, 2)

    def draw(self, surf, fonts):
        getattr(self, "draw_" + self.kind, self.draw_door)(surf)
        self.draw_slots(surf, fonts)

    def draw_door(self, surf):
        frame = pygame.Rect(W // 2 - 110, 60, 220, 220)
        pygame.draw.rect(surf, (60, 50, 80), frame.inflate(30, 20), border_radius=16)
        light = pygame.Surface(frame.size, pygame.SRCALPHA)
        light.fill((255, 230, 150, int(200 * self.open)))
        surf.blit(light, frame)
        half = int(frame.w / 2 * (1 - 0.92 * ease(self.open)))
        for side in (0, 1):
            leaf = pygame.Rect(frame.left if side == 0 else frame.right - half, frame.top, half, frame.h)
            pygame.draw.rect(surf, (110, 92, 140), leaf)
            pygame.draw.rect(surf, (70, 58, 95), leaf, 4)
        if self.open < 0.05:
            pygame.draw.circle(surf, GOLD, frame.center, 14)
            pygame.draw.rect(surf, BG, (frame.centerx - 3, frame.centery - 2, 6, 12))

    def draw_chest(self, surf):
        cx = W // 2
        base = pygame.Rect(cx - 110, 160, 220, 110)
        lift = 50 * ease(self.open)
        if self.open > 0:
            glow = pygame.Surface((260, 160), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 210, 90, int(120 * self.open)), glow.get_rect())
            surf.blit(glow, (cx - 130, 70))
            for i in range(5):
                gy = 150 - lift * 0.9 + math.sin(self.clock * 3 + i) * 4
                pygame.draw.circle(surf, [GOLD, CYAN, GREEN, RED, GOLD][i], (cx - 60 + i * 30, int(gy)), 9)
        pygame.draw.rect(surf, (140, 90, 50), base, border_radius=10)
        pygame.draw.rect(surf, (90, 55, 30), base, 5, border_radius=10)
        lid = pygame.Rect(cx - 116, 110 - lift, 232, 56)
        pygame.draw.rect(surf, (160, 105, 60), lid, border_radius=20)
        pygame.draw.rect(surf, (90, 55, 30), lid, 5, border_radius=20)
        pygame.draw.rect(surf, GOLD, (cx - 14, 150, 28, 30), border_radius=4)

    def draw_boss(self, surf):
        alive = 1 - ease(self.open)
        bx, by = 470, 190 + math.sin(self.clock * 2) * 8
        # người chơi
        pygame.draw.circle(surf, (200, 210, 235), (150, 210), 30)
        pygame.draw.circle(surf, CYAN, (162, 205), 7)
        pygame.draw.polygon(surf, GOLD, [(130, 182), (150, 160), (170, 182)])
        for (k,) in self.shots:
            x = 180 + (bx - 180) * k
            pygame.draw.circle(surf, GOLD, (int(x), int(210 + (by - 210) * k - math.sin(k * math.pi) * 60)), 8)
        if alive > 0.02:
            size = int(80 * (0.4 + 0.6 * alive))
            color = RED if self.flash else (150, 70, 200)
            pygame.draw.polygon(surf, (110, 50, 150), [(bx - size, by - size * 0.6), (bx - size * 1.6, by - size * 1.3), (bx - size * 0.5, by - size * 0.9)])
            pygame.draw.polygon(surf, (110, 50, 150), [(bx + size, by - size * 0.6), (bx + size * 1.6, by - size * 1.3), (bx + size * 0.5, by - size * 0.9)])
            pygame.draw.circle(surf, color, (bx, int(by)), size)
            for ex in (-size // 3, size // 3):
                pygame.draw.circle(surf, WHITE, (bx + ex, int(by - size * 0.15)), max(4, size // 6))
                pygame.draw.circle(surf, BG, (bx + ex - 3, int(by - size * 0.15)), max(2, size // 12))
            pygame.draw.arc(surf, BG, (bx - size // 2, by, size, size // 2), math.pi, math.tau, 3)
        bar = pygame.Rect(370, 70, 200, 14)
        pygame.draw.rect(surf, (60, 30, 40), bar, border_radius=7)
        fill = bar.copy()
        fill.w = int(bar.w * max(0, self.shown_hp) / self.n)
        pygame.draw.rect(surf, RED, fill, border_radius=7)
        pygame.draw.rect(surf, WHITE, bar, 2, border_radius=7)


class IdleScene:
    def __init__(self):
        self.clock = 0.0
        self.done = True

    def update(self, dt):
        self.clock += dt

    def draw(self, surf, fonts):
        for i in range(30):
            x = (i * 97 + self.clock * 12 * (1 + i % 3)) % W
            y = (i * 53) % H
            pygame.draw.circle(surf, (60, 70, 110), (int(x), y), 1 + i % 2)
        title = fonts["big"].render("PYTHON QUEST", True, GOLD)
        surf.blit(title, title.get_rect(center=(W // 2, H // 2 - 14 + math.sin(self.clock * 2) * 4)))
        sub = fonts["small"].render("code  -  run  -  win", True, MUTED)
        surf.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 24)))


# ------------------------------------------------------------------ cầu nối với trang web

def read_command():
    if not WEB:
        return None
    raw = web.window.localStorage.getItem("pq_cmd")
    if not raw or raw in ("null", "undefined"):
        return None
    try:
        return json.loads(str(raw))
    except ValueError:
        return None


def write_status(state, seq=None):
    if WEB:
        web.window.localStorage.setItem("pq_status", json.dumps({"state": state, "seq": seq}))


def build_scene(cmd, fx, banner):
    banner.text = ""
    fx.items.clear()
    if cmd.get("type") == "robot":
        return RobotScene(cmd, fx, banner)
    if cmd.get("type") == "scene":
        return TestScene(cmd, fx, banner)
    return IdleScene()


async def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Python Quest")
    fonts = {"big": pygame.font.Font(None, 40), "mid": pygame.font.Font(None, 30), "small": pygame.font.Font(None, 22)}
    clock = pygame.time.Clock()
    fx, banner = Particles(), Banner()
    scene = IdleScene()
    last_seq = None
    reported = False
    write_status("ready")
    if not WEB:
        scene = build_scene(DEMO[0], fx, banner)

    while True:
        # Tab chạy nền bị trình duyệt giảm FPS: cho dt lớn để animation vẫn tiến kịp.
        dt = min(clock.tick(60) / 1000, 0.25)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and not WEB and pygame.K_1 <= event.key <= pygame.K_4:
                scene = build_scene(DEMO[event.key - pygame.K_1], fx, banner)

        cmd = read_command()
        if cmd and cmd.get("seq") != last_seq:
            last_seq = cmd.get("seq")
            scene = build_scene(cmd, fx, banner)
            reported = False
        if scene.done and not reported and last_seq is not None:
            write_status("done", last_seq)
            reported = True

        scene.update(dt)
        fx.update(dt)
        screen.fill(BG)
        scene.draw(screen, fonts)
        fx.draw(screen)
        banner.draw(screen, fonts, dt)
        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
