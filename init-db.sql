-- UniBot Database Initialization Script
-- Version: 2026.10.21_1

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create database schema for UniBot
CREATE SCHEMA IF NOT EXISTS unibot;

-- Users table
CREATE TABLE IF NOT EXISTS unibot.users (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE,
    password_hash TEXT NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(20),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    avatar_url TEXT
);

-- User groups/roles
CREATE TABLE IF NOT EXISTS unibot.groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB DEFAULT '{}'::jsonb,
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User-Group mapping
CREATE TABLE IF NOT EXISTS unibot.user_groups (
    user_id INTEGER REFERENCES unibot.users(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES unibot.groups(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, group_id)
);

-- Default groups
INSERT INTO unibot.groups (name, description, permissions, is_system) VALUES 
    ('administrators', 'System administrators with full access', '{"admin": true, "manage_users": true, "manage_modules": true, "manage_settings": true}', true),
    ('customers', 'Registered customers', '{"read": true, "use_bot": true, "purchase": true}', true),
    ('anonymous', 'Anonymous users', '{"read": true}', true)
    ON CONFLICT (name) DO NOTHING;

-- Default admin user (password should be hashed in production)
-- This is just a placeholder - actual password should be set via auth module
INSERT INTO unibot.users (username, password_hash, email, full_name, is_active, is_verified) VALUES 
    ('unibotadmin', '$2b$12$default_hash_placeholder_change_me', 'admin@unibot.local', 'UniBot Administrator', true, true)
    ON CONFLICT (username) DO NOTHING;

-- Assign admin to administrators group
INSERT INTO unibot.user_groups (user_id, group_id) 
    SELECT u.id, g.id 
    FROM unibot.users u, unibot.groups g 
    WHERE u.username = 'unibotadmin' AND g.name = 'administrators'
    ON CONFLICT DO NOTHING;

-- Sessions table
CREATE TABLE IF NOT EXISTS unibot.sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES unibot.users(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    platform VARCHAR(50),
    data JSONB DEFAULT '{}'::jsonb,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat platform users (VK, Telegram, MAX)
CREATE TABLE IF NOT EXISTS unibot.chat_users (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES unibot.users(id) ON DELETE SET NULL,
    platform VARCHAR(20) NOT NULL, -- vk, telegram, max
    platform_user_id VARCHAR(100) NOT NULL,
    platform_username VARCHAR(255),
    chat_id VARCHAR(100),
    access_token TEXT,
    refresh_token TEXT,
    token_expires TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (platform, platform_user_id)
);

-- Module registrations
CREATE TABLE IF NOT EXISTS unibot.modules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    version VARCHAR(50) NOT NULL,
    type VARCHAR(50) NOT NULL, -- system, functional
    description TEXT,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    endpoints JSONB DEFAULT '[]'::jsonb,
    config JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    is_required BOOLEAN DEFAULT false,
    last_ping TIMESTAMP WITH TIME ZONE,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Menu structure
CREATE TABLE IF NOT EXISTS unibot.menu_items (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER REFERENCES unibot.menu_items(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    command VARCHAR(255) NOT NULL,
    description TEXT,
    icon VARCHAR(100),
    color VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    required_group VARCHAR(100),
    module_name VARCHAR(100),
    module_command VARCHAR(255),
    params JSONB DEFAULT '{}'::jsonb,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- LLM interactions
CREATE TABLE IF NOT EXISTS unibot.llm_interactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES unibot.users(id) ON DELETE SET NULL,
    chat_user_id INTEGER REFERENCES unibot.chat_users(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES unibot.sessions(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL, -- openai, yandex, local
    model VARCHAR(100) NOT NULL,
    prompt TEXT NOT NULL,
    response TEXT,
    tokens_used INTEGER,
    cost DECIMAL(10, 6),
    duration_ms INTEGER,
    temperature DECIMAL(5, 2),
    top_p DECIMAL(5, 2),
    max_tokens INTEGER,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_username ON unibot.users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON unibot.users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON unibot.users(phone);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON unibot.sessions(token);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON unibot.sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_chat_users_platform ON unibot.chat_users(platform, platform_user_id);
CREATE INDEX IF NOT EXISTS idx_modules_name ON unibot.modules(name);
CREATE INDEX IF NOT EXISTS idx_menu_parent ON unibot.menu_items(parent_id);

-- Audit log
CREATE TABLE IF NOT EXISTS unibot.audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES unibot.users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id INTEGER,
    old_values JSONB DEFAULT '{}'::jsonb,
    new_values JSONB DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45),
    user_agent TEXT,
    status VARCHAR(20) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
DROP TRIGGER IF EXISTS trg_users_updated ON unibot.users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON unibot.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_chat_users_updated ON unibot.chat_users;
CREATE TRIGGER trg_chat_users_updated BEFORE UPDATE ON unibot.chat_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_modules_updated ON unibot.modules;
CREATE TRIGGER trg_modules_updated BEFORE UPDATE ON unibot.modules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_menu_updated ON unibot.menu_items;
CREATE TRIGGER trg_menu_updated BEFORE UPDATE ON unibot.menu_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Log initial setup
INSERT INTO unibot.audit_log (action, entity_type, entity_id, status) 
    VALUES ('database_initialize', 'database', 0, 'success');

COMMENT ON SCHEMA unibot IS 'UniBot main schema containing all module data';

-- Grant permissions (optional, for specific users)
-- These would be set up based on your authentication system
