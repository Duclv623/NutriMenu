CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'USER' CHECK (role IN ('USER', 'ADMIN')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20) NOT NULL CHECK (gender IN ('MALE', 'FEMALE', 'OTHER')),
    height NUMERIC(5, 2) NOT NULL CHECK (height > 0),
    weight NUMERIC(5, 2) NOT NULL CHECK (weight > 0),
    activity_level VARCHAR(20) NOT NULL CHECK (activity_level IN ('SEDENTARY', 'LIGHT', 'MODERATE', 'HIGH', 'VERY_HIGH')),
    goal VARCHAR(20) NOT NULL CHECK (goal IN ('LOSE_WEIGHT', 'MAINTAIN_WEIGHT', 'GAIN_WEIGHT')),
    target_weight NUMERIC(5, 2) CHECK (target_weight > 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE user_allergies (
    user_id UUID NOT NULL REFERENCES user_profiles(user_id),
    ingredient VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, ingredient)
);

CREATE TABLE user_restricted_ingredients (
    user_id UUID NOT NULL REFERENCES user_profiles(user_id),
    ingredient VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, ingredient)
);

CREATE TABLE user_preferences (
    user_id UUID NOT NULL REFERENCES user_profiles(user_id),
    preference VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, preference)
);
