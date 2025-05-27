-- Initialize TimescaleDB and other extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create schema for multi-tenant support
CREATE SCHEMA IF NOT EXISTS public;
CREATE SCHEMA IF NOT EXISTS tenant_template;

-- Set search path
SET search_path TO public;

-- Create base tables with TimescaleDB optimizations
-- These will be created by SQLAlchemy, but we can add TimescaleDB specific features

-- Example: Create a hypertable for conversation messages (time-series data)
-- This will be done after SQLAlchemy creates the tables
-- SELECT create_hypertable('conversation_messages', 'created_at', if_not_exists => TRUE);

-- Example: Create a hypertable for lead activities
-- SELECT create_hypertable('lead_activities', 'created_at', if_not_exists => TRUE);

-- Example: Create a hypertable for property views analytics
-- SELECT create_hypertable('property_views', 'viewed_at', if_not_exists => TRUE);

-- Create continuous aggregates for analytics (examples)
-- These would be created after the main tables exist

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA public TO corretor;
GRANT ALL PRIVILEGES ON SCHEMA tenant_template TO corretor;
GRANT CREATE ON DATABASE corretor_ai_hub TO corretor;

-- Performance tuning for TimescaleDB
ALTER SYSTEM SET timescaledb.max_background_workers = 8;
ALTER SYSTEM SET max_parallel_workers = 8;
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;

-- Enable TimescaleDB telemetry (optional)
ALTER SYSTEM SET timescaledb.telemetry_level = 'off';

-- Reload configuration
SELECT pg_reload_conf();
