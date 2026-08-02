CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(title) <= 180),
    summary TEXT NOT NULL CHECK(length(summary) <= 350),
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    image TEXT,
    featured INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL,
    author TEXT NOT NULL CHECK(length(author) <= 80),
    content TEXT NOT NULL CHECK(length(content) <= 1000),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(news_id) REFERENCES news(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS professionals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    age INTEGER,
    role TEXT NOT NULL,
    address TEXT,
    hours TEXT,
    sections TEXT NOT NULL
);

