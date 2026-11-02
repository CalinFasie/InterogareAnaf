-- InterogareAnaf MVP: un singur tabel, exact 11 coloane.
-- Campurile din adresa sediului social pastreaza numele ANAF.
CREATE TABLE IF NOT EXISTS parteneri (
    cui INTEGER PRIMARY KEY CHECK (cui > 0),
    denumire_initiala TEXT NOT NULL DEFAULT '',
    denumire_anaf TEXT,
    "nrRegCom" TEXT,
    "sdenumire_Localitate" TEXT,
    "sdenumire_Strada" TEXT,
    "snumar_Strada" TEXT,
    "scod_Localitate" TEXT,
    "sdenumire_Judet" TEXT,
    "sdetalii_Adresa" TEXT,
    "scod_Postal" TEXT
);

-- Istoric append-only: o linie pentru fiecare CUI din fiecare incercare de lot.
CREATE TABLE IF NOT EXISTS istoric_verificari (
    id INTEGER PRIMARY KEY,
    cui INTEGER NOT NULL REFERENCES parteneri(cui),
    rulare_id TEXT NOT NULL CHECK (length(rulare_id) > 0),
    incercat_la TEXT NOT NULL CHECK (substr(incercat_la, -1) = 'Z'),
    data_interogarii TEXT NOT NULL CHECK (
        length(data_interogarii) = 10 AND date(data_interogarii) = data_interogarii
    ),
    nr_lot INTEGER NOT NULL CHECK (nr_lot > 0),
    nr_incercare INTEGER NOT NULL CHECK (nr_incercare > 0),
    rezultat TEXT NOT NULL CHECK (rezultat IN ('GASIT', 'NEGASIT', 'EROARE', 'INCOMPLET')),
    http_status INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    cod_eroare TEXT,
    mesaj_eroare TEXT,
    UNIQUE (rulare_id, cui, nr_lot, nr_incercare)
);

CREATE INDEX IF NOT EXISTS idx_istoric_verificari_cui_timp
    ON istoric_verificari (cui, incercat_la);
CREATE INDEX IF NOT EXISTS idx_istoric_verificari_rulare
    ON istoric_verificari (rulare_id, nr_lot, nr_incercare);
CREATE INDEX IF NOT EXISTS idx_istoric_verificari_timp
    ON istoric_verificari (incercat_la);
