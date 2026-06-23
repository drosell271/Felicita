PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE, -- Año neutro 2000: funcionalmente solo se conserva día y mes.
    anniversary_date DATE,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (birth_date IS NOT NULL OR anniversary_date IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_contacts_active ON contacts(active);

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    smtp_host VARCHAR(255),
    smtp_port INTEGER CHECK (smtp_port BETWEEN 1 AND 65535),
    smtp_username VARCHAR(255),
    smtp_password_encrypted TEXT,
    smtp_security VARCHAR(10) NOT NULL DEFAULT 'starttls' CHECK (smtp_security IN ('starttls','ssl','none')),
    sender_email VARCHAR(320),
    company_recipient_email VARCHAR(320),
    sender_name VARCHAR(100) NOT NULL DEFAULT 'Equipo',
    send_time VARCHAR(5) NOT NULL DEFAULT '09:00',
    birthday_subject_template VARCHAR(200) NOT NULL DEFAULT '¡Feliz cumpleaños, {{NOMBRE}}!',
    birthday_body_template TEXT NOT NULL DEFAULT 'Hola {{NOMBRE}}, hoy celebramos tu día.',
    anniversary_subject_template VARCHAR(200) NOT NULL DEFAULT '¡Feliz aniversario, {{NOMBRE}}!',
    anniversary_body_template TEXT NOT NULL DEFAULT 'Hola {{NOMBRE}}, hoy celebramos {{AÑOS}} años de camino compartido.',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS send_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    contact_name VARCHAR(201) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('birthday','anniversary')),
    event_date DATE NOT NULL,
    template_name VARCHAR(100),
    status VARCHAR(20) NOT NULL CHECK (status IN ('processing','sent','failed')),
    error_message TEXT,
    sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_contact_event_day UNIQUE(contact_id, event_type, event_date)
);
CREATE INDEX IF NOT EXISTS ix_send_logs_status ON send_logs(status);
CREATE INDEX IF NOT EXISTS ix_send_logs_contact_id ON send_logs(contact_id);

INSERT OR IGNORE INTO app_settings (id) VALUES (1);
