PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prefixos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefixo TEXT UNIQUE NOT NULL,
    nome TEXT
);

CREATE TABLE IF NOT EXISTS motivos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,
    prefixo_id INTEGER,
    motivo_id INTEGER,
    data TEXT NOT NULL,
    observacao TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY (prefixo_id) REFERENCES prefixos(id) ON DELETE SET NULL,
    FOREIGN KEY (motivo_id) REFERENCES motivos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_registros_data ON registros(data);
CREATE INDEX IF NOT EXISTS idx_registros_numero ON registros(numero);
