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
