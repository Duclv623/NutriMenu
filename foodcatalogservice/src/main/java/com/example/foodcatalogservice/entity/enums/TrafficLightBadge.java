package com.example.foodcatalogservice.entity.enums;

import java.math.BigDecimal;

public enum TrafficLightBadge {
    GREEN_SAFE,          // GI <= 55 và GL <= 10 (An toàn - Khuyên dùng)
    YELLOW_MODERATE,     // GI 56..69 hoặc GL 10..19.9 (Ăn kiểm soát định lượng)
    RED_RESTRICTED;      // GI >= 70 hoặc GL >= 20 (Cần hạn chế tối đa)

    public static TrafficLightBadge evaluate(BigDecimal gi, BigDecimal gl) {
        if (gi.compareTo(new BigDecimal("70.0")) >= 0 || gl.compareTo(new BigDecimal("20.0")) >= 0) {
            return RED_RESTRICTED;
        }
        if (gi.compareTo(new BigDecimal("55.0")) <= 0 && gl.compareTo(new BigDecimal("10.0")) <= 0) {
            return GREEN_SAFE;
        }
        return YELLOW_MODERATE;
    }
}
