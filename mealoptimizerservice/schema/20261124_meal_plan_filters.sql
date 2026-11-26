BEGIN;
CREATE TABLE IF NOT EXISTS meal_plan_excluded_dishes (
    plan_id bigint NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    dish_id bigint NOT NULL,
    PRIMARY KEY (plan_id, dish_id)
);
CREATE TABLE IF NOT EXISTS meal_plan_contraindications (
    plan_id bigint NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    medical_tag varchar(255) NOT NULL,
    PRIMARY KEY (plan_id, medical_tag)
);
COMMIT;
