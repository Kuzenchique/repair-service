-- ============================================================
--  Инициализация БД «Сервисный центр: ремонт компьютерной техники»
--  Выполняется автоматически при ПЕРВОМ запуске контейнера db
--  (скрипты из /docker-entrypoint-initdb.d запускаются только
--   на пустом томе с данными).
-- ============================================================
SET client_encoding = 'UTF8';

-- ---------- Справочники ----------
CREATE TABLE device_types (
    code  VARCHAR(20)  PRIMARY KEY,
    name  VARCHAR(100) NOT NULL
);

CREATE TABLE request_statuses (
    code        VARCHAR(20)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    sort_order  INT          NOT NULL,
    is_final    BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------- Клиенты ----------
CREATE TABLE clients (
    id          SERIAL       PRIMARY KEY,
    full_name   VARCHAR(150) NOT NULL,
    phone       VARCHAR(30)  NOT NULL UNIQUE,
    email       VARCHAR(150),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------- Заявки на обслуживание ----------
CREATE TABLE service_requests (
    id              SERIAL        PRIMARY KEY,
    client_id       INT           NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    device_type     VARCHAR(20)   NOT NULL REFERENCES device_types(code),
    brand_model     VARCHAR(150)  NOT NULL,
    symptoms        TEXT[]        NOT NULL DEFAULT '{}',
    description     TEXT,
    urgency         VARCHAR(10)   NOT NULL DEFAULT 'normal'
                    CHECK (urgency IN ('normal', 'urgent', 'express')),
    estimate_min    INT           CHECK (estimate_min >= 0),
    estimate_max    INT           CHECK (estimate_max >= estimate_min),
    estimate_days   INT,
    diagnosis       TEXT,
    final_cost      INT           CHECK (final_cost >= 0),
    status          VARCHAR(20)   NOT NULL DEFAULT 'new' REFERENCES request_statuses(code),
    master_comment  TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_requests_status  ON service_requests(status);
CREATE INDEX idx_requests_created ON service_requests(created_at DESC);

-- Автоматическое обновление updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_requests_updated_at
    BEFORE UPDATE ON service_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Представление для удобной выборки заявок со всеми названиями
CREATE VIEW v_requests AS
SELECT r.id,
       'SR-' || LPAD(r.id::text, 5, '0') AS number,
       c.full_name AS client_name,
       c.phone     AS client_phone,
       c.email     AS client_email,
       r.device_type,
       d.name      AS device_name,
       r.brand_model,
       r.symptoms,
       r.description,
       r.urgency,
       r.estimate_min,
       r.estimate_max,
       r.estimate_days,
       r.diagnosis,
       r.final_cost,
       r.status,
       s.name      AS status_name,
       s.is_final,
       r.master_comment,
       r.created_at,
       r.updated_at
FROM service_requests r
JOIN clients          c ON c.id   = r.client_id
JOIN device_types     d ON d.code = r.device_type
JOIN request_statuses s ON s.code = r.status;

-- ============================================================
--  Первичные данные
-- ============================================================
INSERT INTO device_types (code, name) VALUES
    ('laptop',  'Ноутбук'),
    ('desktop', 'Системный блок (ПК)'),
    ('aio',     'Моноблок'),
    ('monitor', 'Монитор'),
    ('printer', 'Принтер / МФУ');

INSERT INTO request_statuses (code, name, sort_order, is_final) VALUES
    ('new',           'Новая',                 1, FALSE),
    ('diagnostics',   'Диагностика',           2, FALSE),
    ('in_progress',   'В ремонте',             3, FALSE),
    ('waiting_parts', 'Ожидание запчастей',    4, FALSE),
    ('ready',         'Готово к выдаче',       5, FALSE),
    ('issued',        'Выдано клиенту',        6, TRUE),
    ('cancelled',     'Отменена',              7, TRUE);

INSERT INTO clients (full_name, phone, email) VALUES
    ('Иванов Пётр Сергеевич',        '+7 (915) 123-45-67', 'p.ivanov@mail.ru'),
    ('Смирнова Анна Викторовна',     '+7 (926) 234-56-78', 'anna.smirnova@yandex.ru'),
    ('Кузнецов Дмитрий Олегович',    '+7 (903) 345-67-89', NULL),
    ('Попова Екатерина Андреевна',   '+7 (977) 456-78-90', 'kate.popova@gmail.com'),
    ('ООО «Альфа-Принт»',            '+7 (495) 567-89-01', 'office@alfa-print.ru'),
    ('Соколов Михаил Игоревич',      '+7 (916) 678-90-12', NULL),
    ('Морозова Ольга Николаевна',    '+7 (985) 789-01-23', 'o.morozova@mail.ru'),
    ('Волков Артём Денисович',       '+7 (999) 890-12-34', 'artem.volkov@inbox.ru');

INSERT INTO service_requests
    (client_id, device_type, brand_model, symptoms, description, urgency,
     estimate_min, estimate_max, estimate_days, diagnosis, final_cost, status, master_comment, created_at)
VALUES
    (1, 'laptop', 'ASUS VivoBook 15 X515',
        ARRAY['Сильно греется, выключается под нагрузкой', 'Посторонний шум, треск, гул'],
        'Ноутбук очень шумит и выключается в играх', 'normal',
        3600, 13400, 2, 'Чистка системы охлаждения, замена термопасты; Замена вентилятора (кулера)',
        2900, 'issued', 'Выполнена чистка и замена термопасты', NOW() - INTERVAL '21 days'),
    (2, 'laptop', 'Lenovo IdeaPad 3 15ITL6',
        ARRAY['Не заряжается, работает только от сети'],
        'Батарея не заряжается, индикатор не горит', 'urgent',
        3900, 23100, 1, 'Замена аккумулятора',
        NULL, 'waiting_parts', 'Заказан аккумулятор L20M2PF0', NOW() - INTERVAL '9 days'),
    (3, 'desktop', 'Сборка: Ryzen 5 5600 / B550 / RTX 3060',
        ARRAY['Синий экран, самопроизвольные перезагрузки'],
        'Синий экран MEMORY_MANAGEMENT несколько раз в день', 'normal',
        1500, 21000, 2, 'Тестирование и замена модуля ОЗУ',
        NULL, 'diagnostics', NULL, NOW() - INTERVAL '3 days'),
    (4, 'laptop', 'Apple MacBook Air 13 (2020)',
        ARRAY['Залит жидкостью'],
        'Пролит кофе на клавиатуру, после этого не включается', 'express',
        6700, 35500, 1, 'Чистка платы после залития, восстановление элементов',
        NULL, 'in_progress', 'Следы коррозии в районе цепи питания', NOW() - INTERVAL '1 day'),
    (5, 'printer', 'HP LaserJet Pro MFP M428fdn',
        ARRAY['Замятие бумаги, не захватывает лист', 'Полосы, бледная или грязная печать'],
        'Мнёт бумагу, на отпечатках серые полосы', 'normal',
        3200, 14100, 3, 'Замена роликов подачи бумаги; Чистка / замена печатающей головки или фотобарабана',
        5400, 'ready', 'Заменены ролики и фотобарабан', NOW() - INTERVAL '6 days'),
    (6, 'monitor', 'Samsung S24R350',
        ARRAY['Экран мерцает или гаснет через несколько секунд'],
        'Изображение появляется на секунду и пропадает', 'normal',
        3000, 13500, 3, 'Ремонт подсветки экрана',
        NULL, 'new', NULL, NOW() - INTERVAL '2 hours'),
    (7, 'aio', 'HP 24-cb1000',
        ARRAY['Тормозит, долго загружается', 'Вирусы, всплывающая реклама'],
        'Очень долго включается, постоянно выскакивает реклама в браузере', 'normal',
        5900, 19500, 2, 'Удаление вирусов и рекламного ПО; Замена накопителя на SSD с переносом данных',
        NULL, 'new', NULL, NOW() - INTERVAL '5 hours'),
    (8, 'desktop', 'Dell OptiPlex 7090',
        ARRAY['Не загружается Windows, ошибка загрузки', 'Нужно восстановить данные'],
        'После скачка напряжения не загружается, на диске рабочие документы', 'urgent',
        5200, 39000, 2, 'Восстановление данных с накопителя; Восстановление загрузчика ОС',
        NULL, 'in_progress', 'Диск читается, копируем данные', NOW() - INTERVAL '2 days'),
    (1, 'monitor', 'LG 27UL500-W',
        ARRAY['Не работают USB, HDMI или аудиоразъёмы'],
        'Не определяется по HDMI, по DisplayPort работает', 'normal',
        1200, 3500, 1, 'Замена разъёмов USB / HDMI / аудио',
        NULL, 'cancelled', 'Клиент отказался от ремонта', NOW() - INTERVAL '14 days'),
    (2, 'laptop', 'Acer Aspire 5 A515-56',
        ARRAY['Сломаны петли, трещины корпуса'],
        'Сломалась левая петля, крышка болтается', 'normal',
        3000, 13200, 4, 'Ремонт петель и корпуса',
        4200, 'issued', 'Петля заменена, корпус проклеен', NOW() - INTERVAL '30 days');
