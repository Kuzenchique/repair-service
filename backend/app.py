"""
Backend (REST API) сервисного центра по ремонту компьютерной техники.

Связывает Frontend с базой данных PostgreSQL (заявки на обслуживание)
и с Web-сервисом расчёта ориентировочной стоимости ремонта.
"""
import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
import requests
from flask import Flask, jsonify, request
from psycopg.rows import dict_row

# ---------------- Конфигурация из переменных окружения ----------------
DB_DSN = (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'repair_db')} "
    f"user={os.getenv('DB_USER', 'repair_user')} "
    f"password={os.getenv('DB_PASSWORD', 'repair_pass')}"
)
WEB_SERVICE_URL = os.getenv("WEB_SERVICE_URL", "http://localhost:8001").rstrip("/")
WEB_SERVICE_TIMEOUT = float(os.getenv("WEB_SERVICE_TIMEOUT", "5"))

URGENCY_CODES = ("normal", "urgent", "express")

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False


# ---------------- Вспомогательные функции ----------------
def to_jsonable(value):
    """Приводит значения из БД к виду, пригодному для JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def db_query(sql, params=None, one=False):
    """Выполняет запрос и возвращает строки в виде словарей."""
    with psycopg.connect(DB_DSN, row_factory=dict_row, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
    rows = [to_jsonable(r) for r in rows]
    if one:
        return rows[0] if rows else None
    return rows


def error(message, status=400):
    return jsonify({"error": message}), status


def call_web_service(method, path, payload=None):
    """Запрос к Web-сервису расчёта стоимости. Возвращает (данные, http-код)."""
    url = f"{WEB_SERVICE_URL}{path}"
    resp = requests.request(method, url, json=payload, timeout=WEB_SERVICE_TIMEOUT)
    return resp.json(), resp.status_code


# ---------------- Обработчики ошибок ----------------
@app.errorhandler(404)
def not_found(_):
    return error("Ресурс не найден", 404)


@app.errorhandler(405)
def method_not_allowed(_):
    return error("Метод не поддерживается", 405)


@app.errorhandler(psycopg.Error)
def db_error(exc):
    app.logger.exception("Ошибка БД")
    return error(f"Ошибка базы данных: {exc.__class__.__name__}", 500)


@app.errorhandler(requests.RequestException)
def ws_error(exc):
    app.logger.warning("Web-сервис недоступен: %s", exc)
    return error("Web-сервис расчёта стоимости недоступен", 503)


# ---------------- Служебные эндпоинты ----------------
@app.get("/api")
def index():
    return jsonify({
        "service": "repair-backend",
        "endpoints": [
            "GET    /api/health",
            "GET    /api/requests?status=&q=",
            "GET    /api/requests/<id>",
            "POST   /api/requests",
            "PATCH  /api/requests/<id>",
            "DELETE /api/requests/<id>",
            "GET    /api/stats",
            "GET    /api/statuses",
            "GET    /api/catalog        (из Web-сервиса)",
            "POST   /api/estimate       (через Web-сервис)",
        ],
    })


@app.get("/api/health")
def health():
    result = {"status": "ok", "db": "ok", "web_service": "ok"}
    try:
        db_query("SELECT 1 AS ok")
    except psycopg.Error:
        result["db"] = "unavailable"
        result["status"] = "degraded"
    try:
        call_web_service("GET", "/health")
    except requests.RequestException:
        result["web_service"] = "unavailable"
        result["status"] = "degraded"
    return jsonify(result), (200 if result["db"] == "ok" else 503)


# ---------------- Заявки (CRUD над БД) ----------------
@app.get("/api/requests")
def list_requests():
    conditions, params = [], []
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    if status:
        conditions.append("status = %s")
        params.append(status)
    if q:
        conditions.append("(number ILIKE %s OR client_name ILIKE %s OR client_phone ILIKE %s OR brand_model ILIKE %s)")
        params.extend([f"%{q}%"] * 4)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db_query(f"SELECT * FROM v_requests {where} ORDER BY created_at DESC, id DESC", params)
    return jsonify(rows)


@app.get("/api/requests/<int:request_id>")
def get_request(request_id):
    row = db_query("SELECT * FROM v_requests WHERE id = %s", [request_id], one=True)
    if not row:
        return error("Заявка не найдена", 404)
    return jsonify(row)


@app.post("/api/requests")
def create_request():
    data = request.get_json(silent=True) or {}
    client_name = (data.get("client_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip() or None
    device_type = data.get("device_type")
    brand_model = (data.get("brand_model") or "").strip()
    description = (data.get("description") or "").strip() or None
    urgency = data.get("urgency") or "normal"
    symptoms = data.get("symptoms") or []

    if not client_name:
        return error("Укажите ФИО клиента")
    if not phone:
        return error("Укажите телефон клиента")
    if not brand_model:
        return error("Укажите марку и модель устройства")
    if urgency not in URGENCY_CODES:
        return error("Некорректная срочность")
    if not isinstance(symptoms, list) or not symptoms:
        return error("Выберите хотя бы один симптом")
    if not db_query("SELECT code FROM device_types WHERE code = %s", [device_type], one=True):
        return error("Неизвестный тип устройства")

    # 1. Получаем ориентировочную стоимость от Web-сервиса
    warning = None
    estimate = None
    try:
        data_ws, code = call_web_service("POST", "/api/v1/estimate", {
            "device_type": device_type, "symptoms": symptoms, "urgency": urgency,
        })
        if code != 200:
            return error(data_ws.get("error", "Ошибка расчёта стоимости"), 400)
        estimate = data_ws
    except requests.RequestException:
        warning = "Web-сервис расчёта недоступен: заявка сохранена без оценки стоимости"

    if estimate:
        symptom_names = [s["name"] for s in estimate["symptoms"]]
        main_works = [w["name"] for w in estimate["works"] if w["kind"] == "main"]
        est_min, est_max, est_days = estimate["total_min"], estimate["total_max"], estimate["days"]
        diagnosis = "; ".join(main_works) or None
    else:
        symptom_names = [str(s) for s in symptoms]
        est_min = est_max = est_days = diagnosis = None

    # 2. Сохраняем клиента (или обновляем по телефону) и заявку — в одной транзакции
    with psycopg.connect(DB_DSN, row_factory=dict_row, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO clients (full_name, phone, email) VALUES (%s, %s, %s)
                   ON CONFLICT (phone) DO UPDATE
                       SET full_name = EXCLUDED.full_name,
                           email = COALESCE(EXCLUDED.email, clients.email)
                   RETURNING id""",
                [client_name, phone, email],
            )
            client_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO service_requests
                       (client_id, device_type, brand_model, symptoms, description, urgency,
                        estimate_min, estimate_max, estimate_days, diagnosis)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                [client_id, device_type, brand_model, symptom_names, description, urgency,
                 est_min, est_max, est_days, diagnosis],
            )
            new_id = cur.fetchone()["id"]

    row = db_query("SELECT * FROM v_requests WHERE id = %s", [new_id], one=True)
    body = {"request": row, "estimate": estimate}
    if warning:
        body["warning"] = warning
    return jsonify(body), 201


@app.patch("/api/requests/<int:request_id>")
def update_request(request_id):
    data = request.get_json(silent=True) or {}
    sets, params = [], []

    if "status" in data:
        if not db_query("SELECT code FROM request_statuses WHERE code = %s", [data["status"]], one=True):
            return error("Неизвестный статус")
        sets.append("status = %s")
        params.append(data["status"])
    if "final_cost" in data:
        cost = data["final_cost"]
        if cost in ("", None):
            cost = None
        else:
            try:
                cost = int(cost)
            except (TypeError, ValueError):
                return error("Итоговая стоимость должна быть числом")
            if cost < 0:
                return error("Итоговая стоимость не может быть отрицательной")
        sets.append("final_cost = %s")
        params.append(cost)
    if "master_comment" in data:
        sets.append("master_comment = %s")
        params.append((data["master_comment"] or "").strip() or None)

    if not sets:
        return error("Нет полей для обновления (status, final_cost, master_comment)")

    params.append(request_id)
    updated = db_query(
        f"UPDATE service_requests SET {', '.join(sets)} WHERE id = %s RETURNING id", params, one=True
    )
    if not updated:
        return error("Заявка не найдена", 404)
    return jsonify(db_query("SELECT * FROM v_requests WHERE id = %s", [request_id], one=True))


@app.delete("/api/requests/<int:request_id>")
def delete_request(request_id):
    deleted = db_query("DELETE FROM service_requests WHERE id = %s RETURNING id", [request_id], one=True)
    if not deleted:
        return error("Заявка не найдена", 404)
    return jsonify({"deleted": request_id})


# ---------------- Справочники и статистика ----------------
@app.get("/api/statuses")
def statuses():
    return jsonify(db_query("SELECT code, name, is_final FROM request_statuses ORDER BY sort_order"))


@app.get("/api/stats")
def stats():
    summary = db_query(
        """SELECT COUNT(*)::int                                            AS total,
                  COUNT(*) FILTER (WHERE NOT is_final)::int                AS open,
                  COUNT(*) FILTER (WHERE status = 'ready')::int            AS ready,
                  COALESCE(ROUND(AVG((estimate_min + estimate_max) / 2.0)), 0)::int AS avg_estimate,
                  COALESCE(SUM(final_cost) FILTER (WHERE status = 'issued'), 0)::int AS revenue
           FROM v_requests""",
        one=True,
    )
    by_status = db_query(
        """SELECT s.code, s.name, COUNT(r.id)::int AS count
           FROM request_statuses s
           LEFT JOIN service_requests r ON r.status = s.code
           GROUP BY s.code, s.name, s.sort_order
           ORDER BY s.sort_order"""
    )
    summary["by_status"] = by_status
    return jsonify(summary)


# ---------------- Интеграция с Web-сервисом ----------------
@app.get("/api/catalog")
def catalog():
    data, code = call_web_service("GET", "/api/v1/catalog")
    return jsonify(data), code


@app.post("/api/estimate")
def estimate():
    payload = request.get_json(silent=True) or {}
    data, code = call_web_service("POST", "/api/v1/estimate", payload)
    return jsonify(data), code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
