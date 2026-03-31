-- kommute: KRL arrival board
-- Migration 001: Initial schema
-- PostgreSQL 16+

BEGIN;

-- ============================================================
-- STATIONS
-- 83 Jabodetabek stations + Rangkasbitung
-- ============================================================

CREATE TABLE stations (
    code    VARCHAR(6)  PRIMARY KEY,
    name    VARCHAR(50) NOT NULL
);

-- ============================================================
-- LINES
-- 5 core commuter lines
-- ============================================================

CREATE TABLE lines (
    id      SERIAL      PRIMARY KEY,
    ka_name VARCHAR(50) NOT NULL UNIQUE,
    color   VARCHAR(7)  NOT NULL  -- hex color e.g. #E30A16
);

-- ============================================================
-- STATION_LINES
-- Junction: which stations belong to which lines
-- Stations can appear on multiple lines (e.g. Manggarai on 4)
-- ============================================================

CREATE TABLE station_lines (
    station_id  VARCHAR(6)  NOT NULL REFERENCES stations(code),
    line_id     INTEGER     NOT NULL REFERENCES lines(id),
    PRIMARY KEY (station_id, line_id)
);

-- ============================================================
-- DEST_MAP
-- Maps raw API destination strings to station codes
-- 23 mappings, handles "VIA" routing qualifiers
-- ============================================================

CREATE TABLE dest_map (
    raw_dest            VARCHAR(50) PRIMARY KEY,
    terminal_station_id VARCHAR(6)  NOT NULL REFERENCES stations(code),
    via_station_id      VARCHAR(6)           REFERENCES stations(code)
);

-- ============================================================
-- STOP_TIMES
-- Core table: ~17.5k rows per schedule
-- One row = "train X arrives at station Y at time Z"
-- ============================================================

CREATE TABLE stop_times (
    id              SERIAL      PRIMARY KEY,
    station_id      VARCHAR(6)  NOT NULL REFERENCES stations(code),
    line_id         INTEGER     NOT NULL REFERENCES lines(id),
    train_id        VARCHAR(10) NOT NULL,
    route_name      VARCHAR(60) NOT NULL,
    raw_dest        VARCHAR(50) NOT NULL REFERENCES dest_map(raw_dest),
    arrival_time    TIME        NOT NULL,  -- display: HH:MM:SS
    arrival_sort    INTEGER     NOT NULL,  -- query: minutes since 03:00 operational day
    dest_time       TIME        NOT NULL   -- arrival at final destination
);

-- Covering index: arrival board (Feature 1) + direction grouping (Feature 3)
-- Index-only scan: no heap access needed for the main query
CREATE INDEX idx_arrivals
    ON stop_times (station_id, arrival_sort)
    INCLUDE (train_id, line_id, raw_dest, dest_time, arrival_time, route_name);

-- Covering index: cross-station trip lookup (Feature 4)
-- Self-join on train_id, filter by station_id
CREATE INDEX idx_train_lookup
    ON stop_times (train_id, station_id)
    INCLUDE (arrival_time, arrival_sort, line_id, raw_dest, route_name);

-- ============================================================
-- STOP_TIMES_STAGING
-- Identical structure for zero-downtime table swap on refresh
-- Import new data here, validate, then swap with stop_times
-- ============================================================

CREATE TABLE stop_times_staging (LIKE stop_times INCLUDING ALL);

-- ============================================================
-- SEED: STATIONS
-- ============================================================

INSERT INTO stations (code, name) VALUES
    ('AC',   'ANCOL'),
    ('AK',   'ANGKE'),
    ('BJD',  'BOJONGGEDE'),
    ('BKS',  'BEKASI'),
    ('BKST', 'BEKASI TIMUR'),
    ('BOI',  'BOJONG INDAH'),
    ('BOO',  'BOGOR'),
    ('BPR',  'BATU CEPER'),
    ('BUA',  'BUARAN'),
    ('CBN',  'CIBINONG'),
    ('CC',   'CICAYUR'),
    ('CIT',  'CIBITUNG'),
    ('CJT',  'CILEJIT'),
    ('CKI',  'CIKINI'),
    ('CKR',  'CIKARANG'),
    ('CKY',  'CIKOYA'),
    ('CLT',  'CILEBUT'),
    ('CSK',  'CISAUK'),
    ('CTA',  'CITAYAM'),
    ('CTR',  'CITERAS'),
    ('CUK',  'CAKUNG'),
    ('CW',   'CAWANG'),
    ('DAR',  'DARU'),
    ('DP',   'DEPOK'),
    ('DPB',  'DEPOK BARU'),
    ('DRN',  'DUREN KALIBATA'),
    ('DU',   'DURI'),
    ('GDD',  'GONDANGDIA'),
    ('GGL',  'GROGOL'),
    ('GST',  'GANG SENTIONG'),
    ('JAKK', 'JAKARTA KOTA'),
    ('JAY',  'JAYAKARTA'),
    ('JMU',  'JURANG MANGU'),
    ('JNG',  'JATINEGARA'),
    ('JTK',  'JATAKE'),
    ('JUA',  'JUANDA'),
    ('KAT',  'KARET'),
    ('KBY',  'KEBAYORAN'),
    ('KDS',  'KALIDERES'),
    ('KLD',  'KLENDER'),
    ('KLDB', 'KLENDER BARU'),
    ('KMO',  'KEMAYORAN'),
    ('KMT',  'KRAMAT'),
    ('KPB',  'KAMPUNG BANDAN'),
    ('KRI',  'KRANJI'),
    ('LNA',  'LENTENG AGUNG'),
    ('MGB',  'MANGGA BESAR'),
    ('MJ',   'MAJA'),
    ('MRI',  'MANGGARAI'),
    ('MTR',  'MATRAMAN'),
    ('NMO',  'NAMBO'),
    ('PDRG', 'PONDOK RAJEG'),
    ('PDJ',  'PONDOK RANJI'),
    ('PI',   'PORIS'),
    ('PLM',  'PALMERAH'),
    ('POC',  'PONDOK CINA'),
    ('POK',  'PONDOK JATI'),
    ('PRP',  'PARUNG PANJANG'),
    ('PSE',  'PASAR SENEN'),
    ('PSG',  'PESING'),
    ('PSM',  'PASAR MINGGU'),
    ('PSMB', 'PASAR MINGGU BARU'),
    ('RJW',  'RAJAWALI'),
    ('RK',   'RANGKASBITUNG'),
    ('RU',   'RAWA BUNTU'),
    ('RW',   'RAWA BUAYA'),
    ('SDM',  'SUDIMARA'),
    ('SRP',  'SERPONG'),
    ('SUD',  'SUDIRMAN'),
    ('SUDB', 'SUDIRMAN BARU'),
    ('SW',   'SAWAH BESAR'),
    ('TB',   'TAMBUN'),
    ('TEB',  'TEBET'),
    ('TEJ',  'TENJO'),
    ('TGS',  'TIGARAKSA'),
    ('THB',  'TANAH ABANG'),
    ('THI',  'TANAH TINGGI'),
    ('TKO',  'TAMAN KOTA'),
    ('TLM',  'METLAND TELAGAMURNI'),
    ('TNG',  'TANGERANG'),
    ('TNT',  'TANJUNG BARAT'),
    ('TPK',  'TANJUNG PRIOK'),
    ('UI',   'UNIV. INDONESIA'),
    ('UP',   'UNIV. PANCASILA');

-- ============================================================
-- SEED: LINES (5 core lines)
-- ============================================================

INSERT INTO lines (id, ka_name, color) VALUES
    (1, 'COMMUTER LINE BOGOR',        '#E30A16'),
    (2, 'COMMUTER LINE CIKARANG',     '#0072CE'),
    (3, 'COMMUTER LINE RANGKASBITUNG', '#00A650'),
    (4, 'COMMUTER LINE TANGERANG',    '#F7941D'),
    (5, 'COMMUTER LINE TANJUNGPRIUK', '#DD0067');

-- Reset sequence after explicit id inserts
SELECT setval('lines_id_seq', 5);

-- ============================================================
-- SEED: STATION_LINES
-- Derived from schedule data analysis
-- ============================================================

-- Bogor line (27 stations)
INSERT INTO station_lines (station_id, line_id) VALUES
    ('BJD', 1), ('BOO', 1), ('CBN', 1), ('CKI', 1), ('CLT', 1),
    ('CTA', 1), ('CW',  1), ('DP',  1), ('DPB', 1), ('DRN', 1),
    ('GDD', 1), ('JAKK',1), ('JAY', 1), ('JUA', 1), ('LNA', 1),
    ('MGB', 1), ('MRI', 1), ('NMO', 1), ('PDRG',1), ('POC', 1),
    ('PSM', 1), ('PSMB',1), ('SW',  1), ('TEB', 1), ('TNT', 1),
    ('UI',  1), ('UP',  1);

-- Cikarang line (28 stations)
INSERT INTO station_lines (station_id, line_id) VALUES
    ('AK',  2), ('BKS', 2), ('BKST',2), ('BUA', 2), ('CIT', 2),
    ('CKR', 2), ('CUK', 2), ('DU',  2), ('GST', 2), ('JAKK',2),
    ('JNG', 2), ('KAT', 2), ('KLD', 2), ('KLDB',2), ('KMO', 2),
    ('KMT', 2), ('KPB', 2), ('KRI', 2), ('MRI', 2), ('MTR', 2),
    ('POK', 2), ('PSE', 2), ('RJW', 2), ('SUD', 2), ('SUDB',2),
    ('TB',  2), ('THB', 2), ('TLM', 2);

-- Rangkasbitung line (26 stations)
INSERT INTO station_lines (station_id, line_id) VALUES
    ('AK',  3), ('CC',  3), ('CJT', 3), ('CKY', 3), ('CSK', 3),
    ('CTR', 3), ('DAR', 3), ('DU',  3), ('JMU', 3), ('JTK', 3),
    ('KAT', 3), ('KBY', 3), ('MJ',  3), ('MRI', 3), ('PDJ', 3),
    ('PLM', 3), ('PRP', 3), ('RK',  3), ('RU',  3), ('SDM', 3),
    ('SRP', 3), ('SUD', 3), ('SUDB',3), ('TEJ', 3), ('TGS', 3),
    ('THB', 3);

-- Tangerang line (15 stations)
INSERT INTO station_lines (station_id, line_id) VALUES
    ('BOI', 4), ('BPR', 4), ('DU',  4), ('KAT', 4), ('KDS', 4),
    ('MRI', 4), ('PI',  4), ('PSG', 4), ('RW',  4), ('SUD', 4),
    ('SUDB',4), ('THB', 4), ('THI', 4), ('TKO', 4), ('TNG', 4);

-- Tanjung Priuk line (4 stations)
INSERT INTO station_lines (station_id, line_id) VALUES
    ('AC',  5), ('JAKK',5), ('KPB', 5), ('TPK', 5);

-- ============================================================
-- SEED: DEST_MAP
-- Maps raw API dest strings to terminal + via station codes
-- ============================================================

INSERT INTO dest_map (raw_dest, terminal_station_id, via_station_id) VALUES
    ('ANGKE',                    'AK',   NULL),
    ('ANGKE VIA MRI',            'AK',   'MRI'),
    ('BEKASI',                   'BKS',  NULL),
    ('BEKASI VIA MRI',           'BKS',  'MRI'),
    ('BOGOR',                    'BOO',  NULL),
    ('CIKARANG',                 'CKR',  NULL),
    ('CIKARANG VIA MRI',         'CKR',  'MRI'),
    ('DEPOK',                    'DP',   NULL),
    ('DURI',                     'DU',   NULL),
    ('JAKARTAKOTA',              'JAKK', NULL),
    ('KAMPUNGBANDAN',            'KPB',  NULL),
    ('KAMPUNGBANDAN VIA MRI',    'KPB',  'MRI'),
    ('KAMPUNGBANDAN VIA PSE',    'KPB',  'PSE'),
    ('MANGGARAI',                'MRI',  NULL),
    ('NAMBO',                    'NMO',  NULL),
    ('PARUNGPANJANG',            'PRP',  NULL),
    ('RANGKASBITUNG',            'RK',   NULL),
    ('SERPONG',                  'SRP',  NULL),
    ('TAMBUN',                   'TB',   NULL),
    ('TANAHABANG',               'THB',  NULL),
    ('TANGERANG',                'TNG',  NULL),
    ('TANJUNGPRIUK',             'TPK',  NULL),
    ('TIGARAKSA',                'TGS',  NULL);

COMMIT; 