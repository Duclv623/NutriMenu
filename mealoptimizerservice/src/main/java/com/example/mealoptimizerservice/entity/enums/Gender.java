package com.example.mealoptimizerservice.entity.enums;

import java.math.BigDecimal;

// --- FILE MỚI: Gender.java (Hệ số tính CNLT: Nam x22, Nữ x21) ---
public enum Gender {
    MALE(new BigDecimal("22.0")),   // CNLT Nam = cao(m) * cao(m) * 22
    FEMALE(new BigDecimal("21.0")); // CNLT Nữ  = cao(m) * cao(m) * 21

    private final BigDecimal ibwCoefficient;

    Gender(BigDecimal ibwCoefficient) {
        this.ibwCoefficient = ibwCoefficient;
    }

    public BigDecimal getIbwCoefficient() {
        return ibwCoefficient;
    }
}
