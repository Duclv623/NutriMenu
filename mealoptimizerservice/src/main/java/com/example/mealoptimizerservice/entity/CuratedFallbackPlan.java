package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: CuratedFallbackPlan.java ---
@Entity
@Table(name = "curated_fallback_plans")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CuratedFallbackPlan {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title_vi", nullable = false, length = 200)
    private String titleVi;

    @Column(name = "target_calorie_level", nullable = false)
    private Integer targetCalorieLevel; // VD: 1400, 1600, 1800

    @Column(name = "description_vi", length = 500)
    private String descriptionVi;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "curated_fallback_items", joinColumns = @JoinColumn(name = "curated_plan_id"))
    @Builder.Default
    private List<CuratedDishEntry> entries = new ArrayList<>();

    @Embeddable
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class CuratedDishEntry {
        @Enumerated(EnumType.STRING)
        private MealSlot mealSlot;
        private Long dishId;
        private Integer servingScaledX2;
    }
}
