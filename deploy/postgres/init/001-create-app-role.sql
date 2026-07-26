-- Local production-rehearsal role split.
-- The bootstrap role owns schema and migrations; the app role is non-owner so
-- PostgreSQL row-level security policies are meaningful during local testing.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'thoughtpins_app') THEN
    CREATE ROLE thoughtpins_app LOGIN PASSWORD 'thoughtpins_app';
  END IF;
END
$$;
