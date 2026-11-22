-- Additive PostgreSQL upgrade for checked meal changes.
-- Run against the Optimizer database with a migration account before deployment.
-- Existing meal plans remain readable; their original policy cannot be inferred.
BEGIN;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 0;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS updated_at timestamp DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS change_policy_recorded boolean NOT NULL DEFAULT false;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS template_code varchar(50) DEFAULT 'STANDARD_4_MEALS';
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS max_gi_allowed numeric DEFAULT 50;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS max_daily_gl numeric DEFAULT 80;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS max_daily_sodium_mg numeric DEFAULT 2400;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS max_daily_cholesterol_mg numeric DEFAULT 300;
ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS min_daily_fiber_g numeric DEFAULT 20;
COMMIT;
