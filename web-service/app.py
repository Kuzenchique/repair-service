"""
Web-сервис (по варианту): расчёт ориентировочной стоимости ремонта
компьютерной техники по симптомам.

Эндпоинты:
  GET  /health            — проверка работоспособности (для healthcheck)
  GET  /api/v1/catalog    — справочник устройств, симптомов и срочности
  POST /api/v1/estimate   — расчёт стоимости по симптомам
"""
import math
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from catalog import DEVICES, DIAGNOSTICS_FEE, SYMPTOMS, URGENCY, WORKS

app = Flask(__name__)
app.json.ensure_ascii = False  # кириллица в JSON без \uXXXX

SERVICE_NAME = "repair-estimator"
SERVICE_VERSION = "1.0.0"

# Пороги вероятности для отбора работ
MAIN_THRESHOLD = 0.60      # работа считается основной гипотезой
POSSIBLE_THRESHOLD = 0.25  # работа попадает в список возможных


def round_price(value: float) -> int:
    """Округление цены до 100 рублей."""
    return int(round(value / 100.0)) * 100


def error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION})


@app.get("/api/v1/catalog")
def catalog():
    return jsonify({
        "devices": [{"code": c, "name": d["name"], "coef": d["coef"]} for c, d in DEVICES.items()],
        "urgency": [{"code": c, "name": u["name"], "price_coef": u["price_coef"]} for c, u in URGENCY.items()],
        "symptoms": [
            {"code": c, "name": s["name"], "devices": sorted(s["devices"])}
            for c, s in SYMPTOMS.items()
        ],
        "diagnostics_fee": DIAGNOSTICS_FEE,
    })


def calculate(device: str, symptom_codes: list, urgency: str) -> dict:
    """Основной алгоритм расчёта.

    1. Для каждого симптома берём список вероятных работ, применимых к устройству.
    2. Если одна работа следует из нескольких симптомов, вероятности объединяются:
       P = 1 - П(1 - p_i).
    3. «Основные» работы: самая вероятная работа для каждого симптома и все работы
       с вероятностью >= 60 %. «Возможные»: остальные с вероятностью >= 25 %.
    4. Нижняя граница цены — сумма минимальных цен основных работ,
       верхняя — сумма максимальных цен основных и возможных работ.
    5. Обе границы умножаются на коэффициент устройства и коэффициент срочности.
    """
    dev = DEVICES[device]
    urg = URGENCY[urgency]
    coef = dev["coef"] * urg["price_coef"]

    works = {}          # code -> {"p_not": П(1-p), "because": [...]}
    top_per_symptom = []
    for code in symptom_codes:
        symptom = SYMPTOMS[code]
        candidates = [(w, p) for w, p in symptom["faults"] if device in WORKS[w]["devices"]]
        if not candidates:
            continue
        for w, p in candidates:
            item = works.setdefault(w, {"p_not": 1.0, "because": []})
            item["p_not"] *= (1.0 - p)
            item["because"].append(symptom["name"])
        top_per_symptom.append(max(candidates, key=lambda wp: wp[1])[0])

    result_works = []
    for w, item in works.items():
        prob = 1.0 - item["p_not"]
        if w in top_per_symptom or prob >= MAIN_THRESHOLD:
            kind = "main"
        elif prob >= POSSIBLE_THRESHOLD:
            kind = "possible"
        else:
            continue
        info = WORKS[w]
        result_works.append({
            "code": w,
            "name": info["name"],
            "probability": round(prob * 100),
            "kind": kind,
            "kind_name": "основная" if kind == "main" else "возможная",
            "price_min": round_price(info["min"] * coef),
            "price_max": round_price(info["max"] * coef),
            "days": info["days"],
            "because": item["because"],
        })
    result_works.sort(key=lambda x: (x["kind"] != "main", -x["probability"]))

    main = [w for w in result_works if w["kind"] == "main"]
    possible = [w for w in result_works if w["kind"] == "possible"]

    total_min = sum(w["price_min"] for w in main)
    total_max = sum(w["price_max"] for w in main) + sum(w["price_max"] for w in possible)

    base_days = max((w["days"] for w in main), default=1) + (1 if possible else 0)
    days = max(1, math.ceil(base_days * urg["days_coef"]))

    avg_top = (sum(w["probability"] for w in main) / len(main) / 100) if main else 0
    if avg_top >= 0.70 and len(possible) <= 2:
        confidence = "высокая"
    elif avg_top >= 0.45:
        confidence = "средняя"
    else:
        confidence = "низкая"

    recommendations = []
    if "liquid" in symptom_codes:
        recommendations.append("Не включайте устройство до осмотра мастером — это снизит риск короткого замыкания.")
    if any(w["code"] in ("ssd", "data", "os", "bootloader") for w in result_works):
        recommendations.append("По возможности сделайте резервную копию важных данных перед сдачей в ремонт.")
    if "overheating" in symptom_codes:
        recommendations.append("Профилактическую чистку системы охлаждения рекомендуется делать раз в 1–2 года.")
    if possible:
        recommendations.append("Точный перечень работ определит диагностика: часть возможных работ может не понадобиться.")
    if urgency != "normal":
        recommendations.append(f"Выбрана срочность «{urg['name']}»: цена увеличена в {urg['price_coef']} раза.")

    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "calculated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": {"code": device, "name": dev["name"], "coef": dev["coef"]},
        "urgency": {"code": urgency, "name": urg["name"], "price_coef": urg["price_coef"]},
        "symptoms": [{"code": c, "name": SYMPTOMS[c]["name"]} for c in symptom_codes],
        "works": result_works,
        "diagnostics_fee": DIAGNOSTICS_FEE,
        "total_min": total_min,
        "total_max": total_max,
        "days": days,
        "confidence": confidence,
        "recommendations": recommendations,
        "disclaimer": "Расчёт ориентировочный. Итоговая стоимость определяется после диагностики. "
                      "Диагностика бесплатна при согласии на ремонт.",
    }


@app.post("/api/v1/estimate")
def estimate():
    data = request.get_json(silent=True) or {}
    device = data.get("device_type")
    urgency = data.get("urgency") or "normal"
    symptoms = data.get("symptoms") or []

    if device not in DEVICES:
        return error(f"Неизвестный тип устройства: {device!r}. Допустимо: {', '.join(DEVICES)}")
    if urgency not in URGENCY:
        return error(f"Неизвестная срочность: {urgency!r}. Допустимо: {', '.join(URGENCY)}")
    if not isinstance(symptoms, list) or not symptoms:
        return error("Нужно выбрать хотя бы один симптом")

    # убираем дубли, сохраняя порядок
    symptoms = list(dict.fromkeys(symptoms))
    unknown = [s for s in symptoms if s not in SYMPTOMS]
    if unknown:
        return error(f"Неизвестные симптомы: {', '.join(map(str, unknown))}")
    not_applicable = [SYMPTOMS[s]["name"] for s in symptoms if device not in SYMPTOMS[s]["devices"]]
    if not_applicable:
        return error(f"Симптомы не относятся к устройству «{DEVICES[device]['name']}»: "
                     + "; ".join(not_applicable))

    return jsonify(calculate(device, symptoms, urgency))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
