package com.example.mealoptimizerservice.entity.enums;

import java.math.BigDecimal;

// --- FILE MỚI: PhysicalActivityLevel.java (Nhu cầu năng lượng theo CNLT) ---
public enum PhysicalActivityLevel {
    BEDRIDDEN(new BigDecimal("25.0"), "Nằm tại giường (25 kcal/kg CNLT)"),
    LIGHT(new BigDecimal("30.0"), "Lao động nhẹ - Văn phòng (30 kcal/kg CNLT)"),
    MODERATE(new BigDecimal("35.0"), "Lao động trung bình (35 kcal/kg CNLT)"),
    HEAVY(new BigDecimal("40.0"), "Lao động nặng (40 kcal/kg CNLT)");

    private final BigDecimal kcalPerKgIbw;
    private final String descriptionVi;

    PhysicalActivityLevel(BigDecimal kcalPerKgIbw, String descriptionVi) {
        this.kcalPerKgIbw = kcalPerKgIbw;
        this.descriptionVi = descriptionVi;
    }

    public BigDecimal getKcalPerKgIbw() {
        return kcalPerKgIbw;
    }

    public String getDescriptionVi() {
        return descriptionVi;
    }
}
