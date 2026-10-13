/* Frontend сервисного центра «ТехноРемонт».
 * Все запросы идут на относительный путь /api — nginx проксирует их в контейнер backend.
 */
const API = "/api";

const state = {
  catalog: null,       // справочник из Web-сервиса
  statuses: [],        // статусы заявок из БД
  lastEstimate: null,  // последний расчёт
  lastRequest: null,   // параметры последнего расчёта
  loaded: false,       // заявки уже загружались
};

const $ = (sel) => document.querySelector(sel);
const rub = (n) => (n == null ? "—" : Number(n).toLocaleString("ru-RU"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* пустой ответ */ }
  if (!res.ok) throw new Error((data && data.error) || `Ошибка ${res.status}`);
  return data;
}

function toast(text, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind ? "toast--" + kind : ""}`;
  el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function setBusy(btn, busy, text) {
  if (busy) { if (!btn.disabled) btn.dataset.text = btn.innerHTML; btn.disabled = true; btn.textContent = text; }
  else { btn.disabled = false; btn.innerHTML = btn.dataset.text; }
}

/* ===================== Состояние сервисов ===================== */
async function checkHealth() {
  const mark = (name, ok) => {
    const el = document.querySelector(`.svc[data-svc="${name}"]`);
    el.classList.toggle("is-ok", ok);
    el.classList.toggle("is-bad", !ok);
  };
  mark("frontend", true);
  try {
    const res = await fetch(API + "/health");
    const h = await res.json();
    mark("backend", true);
    mark("db", h.db === "ok");
    mark("web_service", h.web_service === "ok");
  } catch {
    ["backend", "db", "web_service"].forEach((n) => mark(n, false));
  }
}

/* ===================== Справочник и форма расчёта ===================== */
async function loadCatalog() {
  try {
    state.catalog = await api("/catalog");
  } catch (e) {
    $("#symptoms").innerHTML = `<div class="muted">Не удалось загрузить справочник: ${esc(e.message)}</div>`;
    return;
  }
  const { devices, urgency } = state.catalog;
  $("#device").innerHTML = devices.map((d) => `<option value="${d.code}">${esc(d.name)}</option>`).join("");
  $("#urgency").innerHTML = urgency.map((u, i) => {
    const [title, hint] = u.name.split(" (");
    return `<label><input type="radio" name="urgency" value="${u.code}" ${i === 0 ? "checked" : ""}>
      <span>${esc(title)}<small>${hint ? esc(hint.replace(")", "")) : "стандартный срок"}</small></span></label>`;
  }).join("");
  renderSymptoms();
}

function renderSymptoms() {
  const device = $("#device").value;
  const checked = new Set([...document.querySelectorAll("#symptoms input:checked")].map((i) => i.value));
  const list = state.catalog.symptoms.filter((s) => s.devices.includes(device));
  $("#symptoms").innerHTML = list.map((s) => `
    <label class="chk"><input type="checkbox" value="${s.code}" ${checked.has(s.code) ? "checked" : ""}>
    <span>${esc(s.name)}</span></label>`).join("");
  updateSymptomCount();
}

function updateSymptomCount() {
  const n = document.querySelectorAll("#symptoms input:checked").length;
  $("#symptom-count").textContent = n ? `· выбрано: ${n}` : "";
}

/* КНОПКА 2: запрос к Web-сервису (через backend) */
async function onEstimate(ev) {
  ev.preventDefault();
  const symptoms = [...document.querySelectorAll("#symptoms input:checked")].map((i) => i.value);
  if (!symptoms.length) { toast("Отметьте хотя бы один симптом", "error"); return; }
  const payload = {
    device_type: $("#device").value,
    symptoms,
    urgency: document.querySelector('input[name="urgency"]:checked')?.value || "normal",
  };
  const btn = $("#btn-estimate");
  setBusy(btn, true, "Считаем…");
  try {
    const est = await api("/estimate", { method: "POST", body: payload });
    state.lastEstimate = est;
    state.lastRequest = payload;
    renderEstimate(est);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
}

function renderEstimate(est) {
  const works = est.works.map((w) => `
    <li class="work work--${w.kind}">
      <div class="work__name">${esc(w.name)}</div>
      <div class="work__price">${rub(w.price_min)} – ${rub(w.price_max)} ₽</div>
      <div class="work__bar">
        <span class="tag tag--${w.kind}">${esc(w.kind_name)}</span>
        <span class="bar"><i style="width:${w.probability}%"></i></span>
        <span>вероятность ${w.probability}%</span>
      </div>
      <div class="work__why">Причина: ${w.because.map(esc).join("; ")}</div>
    </li>`).join("");

  const recs = est.recommendations.length
    ? `<ul class="notes">${est.recommendations.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : "";

  $("#result-body").innerHTML = `
    <div class="muted">Ориентировочная стоимость · ${esc(est.device.name)}</div>
    <div class="price">
      <span class="price__value">${rub(est.total_min)} – ${rub(est.total_max)}</span><span class="price__cur">₽</span>
    </div>
    <div class="meta">
      <span class="pill">Срок: <b>${est.days} раб. ${daysWord(est.days)}</b></span>
      <span class="pill">Срочность: <b>${esc(est.urgency.name)}</b></span>
      <span class="pill">Точность оценки: <b>${esc(est.confidence)}</b></span>
      <span class="pill">Диагностика: <b>${rub(est.diagnostics_fee)} ₽</b></span>
    </div>
    <ul class="works">${works}</ul>
    ${recs}
    <p class="disclaimer">${esc(est.disclaimer)} Расчёт: ${esc(est.service)} v${esc(est.version)}.</p>

    <form class="order" id="order-form" autocomplete="off">
      <h3>Оформить заявку на ремонт</h3>
      <div class="order__grid">
        <input id="o-name" placeholder="ФИО клиента *" required maxlength="150">
        <input id="o-phone" placeholder="Телефон *" required maxlength="30" inputmode="tel">
        <input id="o-email" placeholder="E-mail" type="email" maxlength="150">
        <input id="o-model" placeholder="Марка и модель устройства *" required maxlength="150">
        <textarea id="o-desc" class="span-2" placeholder="Описание проблемы своими словами"></textarea>
      </div>
      <button class="btn btn--primary btn--block" type="submit" id="btn-order">Оформить заявку и сохранить в БД</button>
    </form>`;
  $("#result-empty").hidden = true;
  $("#result-body").hidden = false;
  $("#order-form").addEventListener("submit", onCreateRequest);
}

function daysWord(n) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "день";
  if ([2, 3, 4].includes(m10) && ![12, 13, 14].includes(m100)) return "дня";
  return "дней";
}

/* Добавление записи в БД */
async function onCreateRequest(ev) {
  ev.preventDefault();
  const btn = $("#btn-order");
  const body = {
    ...state.lastRequest,
    client_name: $("#o-name").value,
    phone: $("#o-phone").value,
    email: $("#o-email").value,
    brand_model: $("#o-model").value,
    description: $("#o-desc").value,
  };
  setBusy(btn, true, "Сохраняем…");
  try {
    const res = await api("/requests", { method: "POST", body });
    toast(`Заявка ${res.request.number} создана`, "ok");
    if (res.warning) toast(res.warning, "error");
    ev.target.reset();
    await loadRequests(res.request.id);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
}

/* ===================== Заявки из БД ===================== */
async function loadStatuses() {
  try {
    state.statuses = await api("/statuses");
    $("#status-filter").innerHTML = `<option value="">Все статусы</option>` +
      state.statuses.map((s) => `<option value="${s.code}">${esc(s.name)}</option>`).join("");
  } catch { /* выведем ошибку при загрузке заявок */ }
}

/* КНОПКА 1: запрос данных из внутренней БД через backend */
async function loadRequests(highlightId = null) {
  const btn = $("#btn-load");
  setBusy(btn, true, "Загрузка…");
  try {
    if (!state.statuses.length) await loadStatuses();
    const params = new URLSearchParams();
    const q = $("#search").value.trim();
    const st = $("#status-filter").value;
    if (q) params.set("q", q);
    if (st) params.set("status", st);
    const [rows, stats] = await Promise.all([api("/requests?" + params), api("/stats")]);
    state.loaded = true;
    renderRequests(rows, highlightId);
    renderStats(stats);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
}

function renderStats(s) {
  const fmt = { total: String, open: String, ready: String, avg_estimate: (v) => rub(v) + " ₽", revenue: (v) => rub(v) + " ₽" };
  document.querySelectorAll("#stats [data-k]").forEach((el) => {
    const k = el.dataset.k;
    el.textContent = fmt[k](s[k]);
  });
}

function renderRequests(rows, highlightId) {
  const tbody = $("#requests");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="table__empty">Заявки не найдены</td></tr>`;
    return;
  }
  const urgLabel = { urgent: "срочно", express: "экспресс" };
  tbody.innerHTML = rows.map((r) => {
    const date = new Date(r.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    const options = state.statuses.map((s) => `<option value="${s.code}" ${s.code === r.status ? "selected" : ""}>${esc(s.name)}</option>`).join("");
    const estimate = r.estimate_min != null ? `${rub(r.estimate_min)} – ${rub(r.estimate_max)}` : "—";
    const final = r.final_cost != null ? `<div class="sub">итог: <b>${rub(r.final_cost)} ₽</b></div>` : "";
    return `
      <tr data-id="${r.id}" class="${r.id === highlightId ? "is-new" : ""}">
        <td><div class="code">${esc(r.number)}</div><div class="sub">${date}</div></td>
        <td>${esc(r.client_name)}<div class="sub">${esc(r.client_phone)}</div></td>
        <td>${esc(r.device_name)}${r.urgency !== "normal" ? `<span class="urg urg--${r.urgency}">${urgLabel[r.urgency]}</span>` : ""}
            <div class="sub">${esc(r.brand_model)}</div></td>
        <td><div class="chips">${r.symptoms.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>
            ${r.diagnosis ? `<div class="diag">→ ${esc(r.diagnosis)}</div>` : ""}
            ${r.master_comment ? `<div class="sub">Мастер: ${esc(r.master_comment)}</div>` : ""}</td>
        <td class="num">${estimate}${r.estimate_days ? `<div class="sub">${r.estimate_days} раб. ${daysWord(r.estimate_days)}</div>` : ""}${final}</td>
        <td><select class="status-select st-${r.status}" data-action="status" aria-label="Статус заявки ${esc(r.number)}">${options}</select></td>
        <td><button class="btn btn--icon" data-action="delete" title="Удалить заявку" aria-label="Удалить заявку ${esc(r.number)}">
          <svg viewBox="0 0 24 24" width="17" height="17"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button></td>
      </tr>`;
  }).join("");
}

/* Изменение статуса и удаление (UPDATE / DELETE в БД) */
async function onTableChange(ev) {
  const sel = ev.target.closest('[data-action="status"]');
  if (!sel) return;
  const id = Number(sel.closest("tr").dataset.id);
  try {
    const r = await api(`/requests/${id}`, { method: "PATCH", body: { status: sel.value } });
    sel.className = `status-select st-${r.status}`;
    toast(`${r.number}: статус «${r.status_name}»`, "ok");
    renderStats(await api("/stats"));
  } catch (e) {
    toast(e.message, "error");
    loadRequests();
  }
}

async function onTableClick(ev) {
  const btn = ev.target.closest('[data-action="delete"]');
  if (!btn) return;
  const tr = btn.closest("tr");
  const number = tr.querySelector(".code").textContent;
  if (!confirm(`Удалить заявку ${number}?`)) return;
  try {
    await api(`/requests/${tr.dataset.id}`, { method: "DELETE" });
    toast(`Заявка ${number} удалена`, "ok");
    loadRequests();
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ===================== Инициализация ===================== */
let searchTimer;
document.addEventListener("DOMContentLoaded", () => {
  $("#estimate-form").addEventListener("submit", onEstimate);
  $("#device").addEventListener("change", renderSymptoms);
  $("#symptoms").addEventListener("change", updateSymptomCount);
  $("#btn-load").addEventListener("click", () => loadRequests());
  $("#status-filter").addEventListener("change", () => state.loaded && loadRequests());
  $("#search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => state.loaded && loadRequests(), 350);
  });
  $("#requests").addEventListener("change", onTableChange);
  $("#requests").addEventListener("click", onTableClick);

  checkHealth();
  setInterval(checkHealth, 15000);
  loadCatalog();
  loadStatuses();
});
