import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "database.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                corp_name TEXT NOT NULL,
                corp_code TEXT NOT NULL,
                stock_code TEXT,
                report_type TEXT,
                filed_at DATE NOT NULL,
                doc_url TEXT,
                pdf_blob BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER REFERENCES filings(id),
                application TEXT,
                product TEXT,
                revenue_share REAL,
                industry_tags TEXT,
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS companies (
                corp_code TEXT PRIMARY KEY,
                corp_name TEXT NOT NULL,
                stock_code TEXT,
                induty_code TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER UNIQUE REFERENCES filings(id),
                competitors TEXT,
                regulations TEXT,
                threats TEXT,
                market_data TEXT,
                news_supplements TEXT,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
