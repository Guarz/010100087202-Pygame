// Python Quest — module dùng chung cho mọi trang: đăng nhập, gọi API, thanh điều hướng.
const TOKEN_KEY = "pq_token";

const PQ = {
  me: null,

  // Giữ để các trang gọi như trước; không còn cấu hình nào cần tải.
  async init() {},

  token() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; }
  },

  async api(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = this.token();
    if (token) headers.Authorization = "Bearer " + token;
    const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      localStorage.removeItem(TOKEN_KEY);
      location.href = "/index.html?next=" + encodeURIComponent(location.pathname + location.search);
      throw new Error(data.detail || "Cần đăng nhập");
    }
    if (!res.ok) throw new Error(errorText(data, res.status));
    return data;
  },

  async login(username, password) {
    const { token } = await this.api("/api/auth/login", { method: "POST", body: { username, password } });
    localStorage.setItem(TOKEN_KEY, token);
  },

  async register(username, password, passwordConfirm) {
    const { token } = await this.api("/api/auth/register", {
      method: "POST", body: { username, password, password_confirm: passwordConfirm },
    });
    localStorage.setItem(TOKEN_KEY, token);
  },

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    location.href = "/index.html";
  },

  // Gọi ở đầu mỗi trang cần đăng nhập. Trả về hồ sơ người dùng.
  async requireUser(active) {
    if (!this.token()) {
      location.href = "/index.html?next=" + encodeURIComponent(location.pathname + location.search);
      return new Promise(() => {});
    }
    try {
      this.me = await this.api("/api/me");
    } catch (err) {
      document.body.innerHTML = `<div class="container py-4"><div class="alert err">${esc(err.message)}</div>
        <button class="btn" onclick="PQ.logout()">Đăng xuất</button></div>`;
      throw err;
    }
    renderNav(this.me, active);
    return this.me;
  },
};

// FastAPI trả lỗi dạng {detail: "..."} hoặc {detail: [{msg: ...}]} (lỗi kiểm tra dữ liệu).
function errorText(data, status) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail) && data.detail.length) return "Dữ liệu không hợp lệ: " + data.detail[0].msg;
  return "Có lỗi xảy ra (" + status + ")";
}

// ---- theme sáng/tối: lưu trong localStorage, áp dụng sớm bằng script nhỏ trong <head> mỗi trang ----
function currentTheme() {
  return document.documentElement.getAttribute("data-bs-theme") === "light" ? "light" : "dark";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-bs-theme", theme);
  try { localStorage.setItem("pq_theme", theme); } catch (_) {}
  document.querySelectorAll(".theme-toggle").forEach(paintThemeButton);
  window.dispatchEvent(new CustomEvent("pq-theme", { detail: theme }));
}

function paintThemeButton(btn) {
  const dark = currentTheme() === "dark";
  const label = dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối";
  btn.innerHTML = icon(dark ? "sun" : "moon");
  btn.title = label;
  btn.setAttribute("aria-label", label);
}

function themeButtonHtml() {
  return '<button type="button" class="btn small ghost theme-toggle"></button>';
}

document.addEventListener("click", (e) => {
  if (e.target.closest(".theme-toggle")) setTheme(currentTheme() === "dark" ? "light" : "dark");
});
document.addEventListener("DOMContentLoaded", () => document.querySelectorAll(".theme-toggle").forEach(paintThemeButton));

// Icon Font Awesome (bộ solid), ví dụ icon("robot").
function icon(name, extra = "") {
  return `<i class="fa-solid fa-${name}${extra ? " " + extra : ""}" aria-hidden="true"></i>`;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(message, ms = 2600) {
  const el = document.createElement("div");
  el.className = "pq-toast";
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function renderNav(me, active) {
  const links = [
    ["map", "/map.html", icon("map") + " Bản đồ"],
    ["leaderboard", "/leaderboard.html", icon("trophy") + " Bảng xếp hạng"],
  ];
  if (me.role === "admin") links.push(["admin", "/admin.html", icon("shield-halved") + " Quản trị"]);
  const nav = document.createElement("nav");
  nav.className = "navbar navbar-expand-lg sticky-top pq-navbar";
  nav.innerHTML = `
    <div class="container-fluid px-3 px-lg-4">
      <a class="navbar-brand" href="/map.html">Python<span>Quest</span></a>
      <div class="d-lg-none ms-auto me-2">${themeButtonHtml()}</div>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#pq-nav"
              aria-controls="pq-nav" aria-expanded="false" aria-label="Mở menu">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="pq-nav">
        <ul class="navbar-nav me-auto gap-1 my-2 my-lg-0">${links.map(([id, href, label]) =>
          `<li class="nav-item"><a class="nav-link ${id === active ? "active" : ""}" href="${href}">${label}</a></li>`).join("")}</ul>
        <div class="d-flex align-items-center flex-wrap gap-2 pb-2 pb-lg-0">
          <span class="chip gold">${icon("star")} ${me.score} điểm</span>
          ${me.role === "admin" ? '<span class="chip admin">admin</span>' : ""}
          <span class="text-truncate" style="max-width:160px">${esc(me.display_name)}</span>
          <span class="d-none d-lg-inline">${themeButtonHtml()}</span>
          <button class="btn small ghost ms-auto ms-lg-0" id="logout">${icon("right-from-bracket")} Đăng xuất</button>
        </div>
      </div>
    </div>`;
  document.body.prepend(nav);
  nav.querySelectorAll(".theme-toggle").forEach(paintThemeButton);
  nav.querySelector("#logout").onclick = () => PQ.logout();
}
