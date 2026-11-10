package com.example.foodcatalogservice.entity.enums;

import java.math.BigDecimal;

public enum GiLevel {
    NONE, LOW, MEDIUM, HIGH;

    public static GiLevel fromValue(BigDecimal gi) {
        if (gi == null || gi.compareTo(BigDecimal.ZERO) <= 0) return NONE;
        if (gi.compareTo(new BigDecimal("55.0")) <= 0) return LOW;
        if (gi.compareTo(new BigDecimal("69.9")) <= 0) return MEDIUM;
        return HIGH;
    }
}
