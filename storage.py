import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / 'customer_service.db'


def utcnow():
    return datetime.utcnow().isoformat(timespec='seconds')


class Storage:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    account_id TEXT,
                    account_name TEXT,
                    login_status TEXT NOT NULL DEFAULT 'idle',
                    listen_status TEXT NOT NULL DEFAULT 'offline',
                    auto_reply_enabled INTEGER NOT NULL DEFAULT 1,
                    ai_reply_enabled INTEGER NOT NULL DEFAULT 0,
                    last_login_at TEXT,
                    last_heartbeat_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL UNIQUE,
                    buyer_id TEXT NOT NULL,
                    buyer_name TEXT NOT NULL,
                    item_id TEXT,
                    item_title TEXT,
                    item_url TEXT,
                    item_cover TEXT,
                    item_context_source TEXT,
                    status TEXT NOT NULL DEFAULT 'auto',
                    auto_reply_enabled INTEGER NOT NULL DEFAULT 1,
                    manual_takeover INTEGER NOT NULL DEFAULT 0,
                    bargain_count INTEGER NOT NULL DEFAULT 0,
                    last_intent TEXT,
                    last_message_at TEXT,
                    last_message_preview TEXT,
                    unread_count INTEGER NOT NULL DEFAULT 0,
                    context_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    platform_message_id TEXT,
                    sender_type TEXT NOT NULL,
                    sender_id TEXT,
                    sender_name TEXT,
                    message_type TEXT NOT NULL DEFAULT 'text',
                    content TEXT NOT NULL,
                    raw_payload TEXT,
                    reply_source TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reply_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS faq_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    doc_type TEXT NOT NULL DEFAULT 'faq',
                    tags TEXT,
                    match_keywords TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reply_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    message_id INTEGER,
                    reply_message_id INTEGER,
                    reply_source TEXT NOT NULL,
                    matched_rule_id INTEGER,
                    matched_doc_id INTEGER,
                    ai_model TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS system_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT NOT NULL UNIQUE,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    price TEXT,
                    cover TEXT,
                    item_url TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)
        self.seed_defaults()

    def _migrate_schema(self, conn):
        expected = {
            'conversations': {
                'item_url': "ALTER TABLE conversations ADD COLUMN item_url TEXT",
                'item_cover': "ALTER TABLE conversations ADD COLUMN item_cover TEXT",
                'item_context_source': "ALTER TABLE conversations ADD COLUMN item_context_source TEXT",
                'bargain_count': "ALTER TABLE conversations ADD COLUMN bargain_count INTEGER NOT NULL DEFAULT 0",
                'last_intent': "ALTER TABLE conversations ADD COLUMN last_intent TEXT",
            },
            'items': {},
        }
        for table, additions in expected.items():
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            columns = {row[1] for row in rows}
            for column, ddl in additions.items():
                if column not in columns:
                    conn.execute(ddl)

    def seed_defaults(self):
        now = utcnow()
        defaults = {
            'auto_reply_enabled': '1',
            'ai_reply_enabled': '0',
            'default_reply_text': '你好，消息已收到，我稍后回复你。',
            'manual_fallback_text': '这个问题我先帮你记录，稍后人工回复你。',
            'ai_api_url': '',
            'ai_api_key': '',
            'ai_model': '',
            'ai_system_prompt': '你是闲鱼卖家的客服助手。回复要简短、礼貌、自然，不要编造库存、发货、优惠或售后承诺。',
        }
        with self.connect() as conn:
            for key, value in defaults.items():
                conn.execute(
                    """
                    INSERT INTO system_settings (setting_key, setting_value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(setting_key) DO NOTHING
                    """,
                    (key, value, now),
                )
        self._seed_rule_defaults()
        self._seed_faq_defaults()
        self.ensure_primary_account()

    def _seed_rule_defaults(self):
        rows = [
            ('问候语', 'keyword', ['在吗', '有人吗', '在不在'], '你好，在的，请说下你想咨询的商品或问题。', 10),
            ('价格咨询', 'keyword', ['价格', '多少钱', '最低', '便宜点'], '价格以商品页面为准，如果你想确认优惠空间，可以把你看的商品发我。', 20),
            ('发货咨询', 'keyword', ['发货', '多久发', '什么时候发'], '正常会尽快安排处理，具体发货时间我会尽快确认后回复你。', 30),
            ('运费咨询', 'keyword', ['包邮', '邮费', '运费'], '邮费和发货方式以商品页说明为准，你也可以把商品链接发我，我帮你确认。', 40),
            ('敏感问题', 'sensitive', ['退款', '投诉', '差评', '平台介入', '假货', '骗子'], '这个问题我先帮你记录，稍后人工回复你。', 5),
        ]
        with self.connect() as conn:
            exists = conn.execute("SELECT COUNT(*) AS c FROM reply_rules").fetchone()['c']
            if exists:
                return
            for name, rule_type, keywords, reply, priority in rows:
                conn.execute(
                    """
                    INSERT INTO reply_rules
                    (rule_name, rule_type, keywords, reply_text, priority, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (name, rule_type, json.dumps(keywords, ensure_ascii=False), reply, priority, utcnow(), utcnow()),
                )

    def _seed_faq_defaults(self):
        rows = [
            ('默认发货说明', '正常会尽快安排处理，具体发货时间以实际情况为准。', 'faq', '发货,多久发,什么时候发'),
            ('默认售后说明', '售后和商品情况以页面说明为准，如有特殊问题我会尽快帮你确认。', 'faq', '售后,退货,保修'),
        ]
        with self.connect() as conn:
            exists = conn.execute("SELECT COUNT(*) AS c FROM faq_docs").fetchone()['c']
            if exists:
                return
            for title, content, doc_type, keywords in rows:
                conn.execute(
                    """
                    INSERT INTO faq_docs
                    (title, content, doc_type, tags, match_keywords, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, '', ?, 1, ?, ?)
                    """,
                    (title, content, doc_type, keywords, utcnow(), utcnow()),
                )

    def ensure_primary_account(self):
        now = utcnow()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM accounts WHERE platform = 'xianyu' LIMIT 1").fetchone()
            if row:
                return
            conn.execute(
                """
                INSERT INTO accounts
                (platform, account_id, account_name, login_status, listen_status, auto_reply_enabled, ai_reply_enabled, created_at, updated_at)
                VALUES ('xianyu', '', '', 'idle', 'offline', 1, 0, ?, ?)
                """,
                (now, now),
            )

    def fetchone(self, query, params=()):
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    def fetchall(self, query, params=()):
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def execute(self, query, params=()):
        with self.connect() as conn:
            cur = conn.execute(query, params)
            return cur.lastrowid
