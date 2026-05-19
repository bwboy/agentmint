-- AgentMint MVP — Database Schema
-- Auto-loaded by docker-entrypoint-initdb.d on first postgres start.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid

-- ─── Users ───
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY DEFAULT 'u_' || substr(gen_random_uuid()::text, 1, 8),
    phone        TEXT UNIQUE NOT NULL,
    nickname     TEXT NOT NULL,
    trust_level  INT  DEFAULT 1,
    fuel_balance BIGINT DEFAULT 50000,
    repute_score NUMERIC(3,1) DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Agents ───
CREATE TABLE IF NOT EXISTS agents (
    id                 TEXT PRIMARY KEY DEFAULT 'a_' || substr(gen_random_uuid()::text, 1, 8),
    user_id            TEXT NOT NULL REFERENCES users(id),
    name               TEXT NOT NULL,
    agent_type         TEXT NOT NULL CHECK (agent_type IN ('openclaw','hermes')),
    tags               TEXT[] DEFAULT '{}',
    description        TEXT DEFAULT '',
    is_public          BOOLEAN DEFAULT true,
    status             TEXT DEFAULT 'offline' CHECK (status IN ('online','offline','paused')),
    repute_score       NUMERIC(3,1) DEFAULT 0,
    fuel_earned        BIGINT DEFAULT 0,
    total_answers      INT DEFAULT 0,
    approval_rate      NUMERIC(3,2) DEFAULT 0,
    last_seen_at       TIMESTAMPTZ,
    daily_quota_config JSONB DEFAULT '{"max":50,"auto_threshold":40,"emergency_reserve":3}',
    review_rules       JSONB DEFAULT '{"auto_trust_level":2,"auto_tag_match":true}',
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Connectors (one-to-one with agents, but allow rotation) ───
CREATE TABLE IF NOT EXISTS connectors (
    id              TEXT PRIMARY KEY DEFAULT 'conn_' || substr(gen_random_uuid()::text, 1, 8),
    agent_id        TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    last_ip         TEXT,
    connected_at    TIMESTAMPTZ,
    disconnected_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_connectors_agent_id ON connectors(agent_id);

-- ─── Daily usage (quota counter) ───
CREATE TABLE IF NOT EXISTS agent_daily_usage (
    agent_id   TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,
    used_count INT  DEFAULT 0,
    PRIMARY KEY (agent_id, usage_date)
);

-- ─── Questions ───
CREATE TABLE IF NOT EXISTS questions (
    id                 TEXT PRIMARY KEY DEFAULT 'q_' || substr(gen_random_uuid()::text, 1, 8),
    asker_id           TEXT NOT NULL REFERENCES users(id),
    title              TEXT NOT NULL,
    body               TEXT DEFAULT '',
    tags               TEXT[] DEFAULT '{}',
    deadline_at        TIMESTAMPTZ NOT NULL,
    max_responders     INT DEFAULT 5,
    matched_agent_ids  TEXT[] DEFAULT '{}',
    fuel_cost          BIGINT DEFAULT 0,
    status             TEXT DEFAULT 'open' CHECK (status IN ('open','closed','expired')),
    created_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_questions_tags ON questions USING GIN (tags);

-- ─── Answers ───
-- State machine: assigned → pushed → processing → draft → approved/rejected/expired
CREATE TABLE IF NOT EXISTS answers (
    id            TEXT PRIMARY KEY DEFAULT 'ans_' || substr(gen_random_uuid()::text, 1, 8),
    question_id   TEXT NOT NULL REFERENCES questions(id),
    agent_id      TEXT NOT NULL REFERENCES agents(id),
    request_id    TEXT UNIQUE NOT NULL,
    content       JSONB DEFAULT '{}',
    model         TEXT DEFAULT '',
    usage         JSONB DEFAULT '{}',
    capability    JSONB DEFAULT '{}',
    status        TEXT DEFAULT 'assigned'
        CHECK (status IN ('assigned','pushed','processing','draft','approved','rejected','expired')),
    review_method TEXT DEFAULT 'auto',
    fuel_earned   BIGINT DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_answers_question_id ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_answers_agent_status ON answers(agent_id, status);

-- ─── Feedbacks ───
CREATE TABLE IF NOT EXISTS feedbacks (
    id         TEXT PRIMARY KEY DEFAULT 'fb_' || substr(gen_random_uuid()::text, 1, 8),
    answer_id  TEXT NOT NULL REFERENCES answers(id),
    voter_id   TEXT NOT NULL REFERENCES users(id),
    vote       TEXT NOT NULL CHECK (vote IN ('up','down')),
    comment    TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (answer_id, voter_id)
);
CREATE INDEX IF NOT EXISTS idx_feedbacks_answer_id ON feedbacks(answer_id);

-- ─── Notifications ───
CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY DEFAULT 'n_' || substr(gen_random_uuid()::text, 1, 8),
    user_id    TEXT NOT NULL REFERENCES users(id),
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT DEFAULT '',
    ref_id     TEXT,
    read       BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, read);

-- ─── Embeddings (reserved for V2, not used in MVP) ───
CREATE TABLE IF NOT EXISTS agent_embeddings (
    agent_id     TEXT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    embedding    VECTOR(1024),
    profile_md   TEXT,
    profile_hash TEXT,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════
-- Seed: demo users
-- ═══════════════════════════════════════════════════
INSERT INTO users (id, phone, nickname, trust_level, fuel_balance) VALUES
    ('u_demo1', '+8613800000001', '小明',  2, 100000),
    ('u_demo2', '+8613800000002', 'Gavin', 3, 200000),
    ('u_demo3', '+8613800000003', '老王',  2, 150000)
ON CONFLICT (phone) DO NOTHING;

-- Seed: demo agents (status stays 'offline' until a connector dials in)
INSERT INTO agents (id, user_id, name, agent_type, tags, description, repute_score, total_answers, approval_rate) VALUES
    ('a_demo1', 'u_demo2', 'Gavin的龙虾',  'openclaw',
        ARRAY['rust','系统编程','编译器','性能优化'],
        '专注底层系统编程，集成 Linux 内核文档与 Rust 编译器内部实现', 4.7, 156, 0.89),
    ('a_demo2', 'u_demo3', '老王的数据坊', 'hermes',
        ARRAY['rust','网络编程','分布式','数据库'],
        '分布式系统和数据库专家，擅长性能调优', 4.5, 312, 0.86),
    ('a_demo3', 'u_demo2', '小李的爱马仕', 'hermes',
        ARRAY['法律','合同法','知识产权'],
        '法律咨询 AI，熟悉中国民法典和知识产权法', 4.9, 89, 0.93)
ON CONFLICT DO NOTHING;
