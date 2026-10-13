"""
Справочники Web-сервиса «Расчёт ориентировочной стоимости ремонта».

Тематика: ремонт компьютерной техники.
Здесь описаны типы устройств, виды работ (с ценовыми диапазонами)
и симптомы неисправностей с вероятностями связанных с ними работ.
"""

# Типы устройств и коэффициент сложности ремонта
DEVICES = {
    "laptop":  {"name": "Ноутбук",              "coef": 1.20},
    "desktop": {"name": "Системный блок (ПК)",  "coef": 1.00},
    "aio":     {"name": "Моноблок",             "coef": 1.30},
    "monitor": {"name": "Монитор",              "coef": 1.00},
    "printer": {"name": "Принтер / МФУ",        "coef": 0.90},
}

# Срочность: коэффициент цены и коэффициент срока
URGENCY = {
    "normal":  {"name": "Обычная",                      "price_coef": 1.0, "days_coef": 1.0},
    "urgent":  {"name": "Срочная (1–2 дня)",            "price_coef": 1.3, "days_coef": 0.5},
    "express": {"name": "Экспресс (в день обращения)",  "price_coef": 1.6, "days_coef": 0.25},
}

# Стоимость диагностики (бесплатно при согласии на ремонт)
DIAGNOSTICS_FEE = 700

ALL = {"laptop", "desktop", "aio", "monitor", "printer"}
PC = {"laptop", "desktop", "aio"}

# Виды работ: название, базовая цена «от–до» (руб., с типовыми комплектующими),
# срок в рабочих днях и типы устройств, к которым работа применима.
WORKS = {
    "psu":           {"name": "Ремонт или замена блока питания",                       "min": 2500, "max": 6500,  "days": 1, "devices": {"desktop", "aio", "monitor", "printer"}},
    "adapter":       {"name": "Замена внешнего блока питания (зарядного устройства)",   "min": 1500, "max": 4000,  "days": 1, "devices": {"laptop"}},
    "mb_power":      {"name": "Ремонт цепей питания материнской платы",                "min": 4000, "max": 9500,  "days": 3, "devices": PC},
    "charge_port":   {"name": "Замена разъёма питания / зарядки",                      "min": 1500, "max": 3500,  "days": 1, "devices": {"laptop"}},
    "battery":       {"name": "Замена аккумулятора",                                   "min": 2500, "max": 6500,  "days": 1, "devices": {"laptop"}},
    "gpu":           {"name": "Ремонт видеоподсистемы (реболл / замена видеочипа)",     "min": 6000, "max": 18000, "days": 5, "devices": PC},
    "ram":           {"name": "Тестирование и замена модуля ОЗУ",                      "min": 1500, "max": 5000,  "days": 1, "devices": PC},
    "cable":         {"name": "Замена шлейфа матрицы / видеокабеля",                   "min": 1500, "max": 4000,  "days": 2, "devices": {"laptop", "aio"}},
    "matrix":        {"name": "Замена матрицы (экрана)",                               "min": 5000, "max": 16000, "days": 3, "devices": {"laptop", "aio", "monitor"}},
    "backlight":     {"name": "Ремонт подсветки экрана",                               "min": 3000, "max": 7500,  "days": 2, "devices": {"laptop", "aio", "monitor"}},
    "monitor_board": {"name": "Ремонт платы управления монитора",                      "min": 2500, "max": 6000,  "days": 2, "devices": {"monitor"}},
    "cooling":       {"name": "Чистка системы охлаждения, замена термопасты",           "min": 1500, "max": 3000,  "days": 1, "devices": PC},
    "fan":           {"name": "Замена вентилятора (кулера)",                           "min": 1500, "max": 3500,  "days": 1, "devices": PC},
    "os":            {"name": "Переустановка ОС и драйверов",                          "min": 1500, "max": 2500,  "days": 1, "devices": PC},
    "ssd":           {"name": "Замена накопителя на SSD с переносом данных",           "min": 3500, "max": 8000,  "days": 1, "devices": PC},
    "bootloader":    {"name": "Восстановление загрузчика ОС",                          "min": 1000, "max": 2000,  "days": 1, "devices": PC},
    "virus":         {"name": "Удаление вирусов и рекламного ПО",                      "min": 1000, "max": 2500,  "days": 1, "devices": PC},
    "keyboard":      {"name": "Замена клавиатуры",                                     "min": 2500, "max": 6500,  "days": 2, "devices": {"laptop"}},
    "touchpad":      {"name": "Ремонт тачпада",                                        "min": 1500, "max": 4000,  "days": 2, "devices": {"laptop"}},
    "liquid":        {"name": "Чистка платы после залития, восстановление элементов",  "min": 3500, "max": 12000, "days": 4, "devices": PC},
    "wifi":          {"name": "Ремонт или замена Wi-Fi модуля",                        "min": 1500, "max": 3500,  "days": 1, "devices": PC},
    "ports":         {"name": "Замена разъёмов USB / HDMI / аудио",                    "min": 1200, "max": 3500,  "days": 1, "devices": {"laptop", "desktop", "aio", "monitor"}},
    "data":          {"name": "Восстановление данных с накопителя",                    "min": 3000, "max": 15000, "days": 3, "devices": PC},
    "hinges":        {"name": "Ремонт петель и корпуса",                               "min": 2500, "max": 7000,  "days": 3, "devices": {"laptop"}},
    "rollers":       {"name": "Замена роликов подачи бумаги",                          "min": 1500, "max": 3500,  "days": 1, "devices": {"printer"}},
    "printhead":     {"name": "Чистка / замена печатающей головки или фотобарабана",   "min": 2000, "max": 6500,  "days": 2, "devices": {"printer"}},
    "fuser":         {"name": "Ремонт узла термозакрепления (печки)",                  "min": 2500, "max": 6000,  "days": 2, "devices": {"printer"}},
    "printer_board": {"name": "Ремонт платы управления принтера",                      "min": 3000, "max": 7000,  "days": 3, "devices": {"printer"}},
}

# Симптомы: название, применимые устройства и вероятные работы (код работы, вероятность)
SYMPTOMS = {
    "no_power": {
        "name": "Не включается, не реагирует на кнопку",
        "devices": ALL,
        "faults": [("psu", 0.45), ("adapter", 0.35), ("mb_power", 0.40),
                   ("charge_port", 0.25), ("monitor_board", 0.40), ("printer_board", 0.35)],
    },
    "no_image": {
        "name": "Включается, но нет изображения",
        "devices": {"laptop", "desktop", "aio", "monitor"},
        "faults": [("gpu", 0.40), ("ram", 0.35), ("cable", 0.25), ("backlight", 0.30),
                   ("monitor_board", 0.45)],
    },
    "screen_damage": {
        "name": "Разбит экран, полосы или пятна на изображении",
        "devices": {"laptop", "aio", "monitor"},
        "faults": [("matrix", 0.80), ("cable", 0.30), ("monitor_board", 0.25)],
    },
    "flicker": {
        "name": "Экран мерцает или гаснет через несколько секунд",
        "devices": {"laptop", "aio", "monitor"},
        "faults": [("backlight", 0.60), ("cable", 0.40), ("monitor_board", 0.35)],
    },
    "overheating": {
        "name": "Сильно греется, выключается под нагрузкой",
        "devices": PC,
        "faults": [("cooling", 0.85), ("fan", 0.35)],
    },
    "noise": {
        "name": "Посторонний шум, треск, гул",
        "devices": {"laptop", "desktop", "aio", "printer"},
        "faults": [("fan", 0.60), ("ssd", 0.35), ("rollers", 0.45)],
    },
    "slow": {
        "name": "Тормозит, долго загружается",
        "devices": PC,
        "faults": [("os", 0.50), ("ssd", 0.55), ("virus", 0.35), ("cooling", 0.30)],
    },
    "bsod": {
        "name": "Синий экран, самопроизвольные перезагрузки",
        "devices": PC,
        "faults": [("ram", 0.45), ("os", 0.40), ("ssd", 0.30), ("cooling", 0.25), ("psu", 0.20)],
    },
    "no_boot": {
        "name": "Не загружается Windows, ошибка загрузки",
        "devices": PC,
        "faults": [("bootloader", 0.50), ("os", 0.45), ("ssd", 0.40)],
    },
    "virus": {
        "name": "Вирусы, всплывающая реклама",
        "devices": PC,
        "faults": [("virus", 0.90), ("os", 0.25)],
    },
    "no_charge": {
        "name": "Не заряжается, работает только от сети",
        "devices": {"laptop"},
        "faults": [("battery", 0.50), ("charge_port", 0.45), ("adapter", 0.35), ("mb_power", 0.20)],
    },
    "keyboard": {
        "name": "Не работают клавиши или тачпад",
        "devices": {"laptop"},
        "faults": [("keyboard", 0.70), ("touchpad", 0.30), ("liquid", 0.20)],
    },
    "liquid": {
        "name": "Залит жидкостью",
        "devices": {"laptop", "aio"},
        "faults": [("liquid", 0.95), ("keyboard", 0.50)],
    },
    "wifi": {
        "name": "Не работает Wi-Fi или сеть",
        "devices": PC,
        "faults": [("wifi", 0.70), ("os", 0.25)],
    },
    "ports": {
        "name": "Не работают USB, HDMI или аудиоразъёмы",
        "devices": {"laptop", "desktop", "aio", "monitor"},
        "faults": [("ports", 0.80), ("os", 0.15)],
    },
    "data_loss": {
        "name": "Нужно восстановить данные",
        "devices": PC,
        "faults": [("data", 0.95)],
    },
    "hinges": {
        "name": "Сломаны петли, трещины корпуса",
        "devices": {"laptop"},
        "faults": [("hinges", 0.90), ("cable", 0.20)],
    },
    "paper_jam": {
        "name": "Замятие бумаги, не захватывает лист",
        "devices": {"printer"},
        "faults": [("rollers", 0.80), ("printer_board", 0.15)],
    },
    "print_quality": {
        "name": "Полосы, бледная или грязная печать",
        "devices": {"printer"},
        "faults": [("printhead", 0.75), ("fuser", 0.30)],
    },
}
