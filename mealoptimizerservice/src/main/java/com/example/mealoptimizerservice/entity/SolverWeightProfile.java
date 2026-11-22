package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: SolverWeightProfile.java ---
@Entity
@Table(name = "solver_weight_profiles")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SolverWeightProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String code;

    @Column(name = "name_vi", nullable = false, length = 150)
    private String nameVi;

    @Builder.Default
    @Column(name = "weight_carb_deviation", nullable = false)
    private Long weightCarbDeviation = 50L; // w1: Ưu tiên số 1 - Kiểm soát đường huyết

    @Builder.Default
    @Column(name = "weight_glycemic_load", nullable = false)
    private Long weightGlycemicLoad = 30L;  // w2: Giảm tổng GL

    @Builder.Default
    @Column(name = "weight_calorie_deviation", nullable = false)
    private Long weightCalorieDeviation = 10L; // w3: Cân bằng năng lượng TDEE

    @Builder.Default
    @Column(name = "weight_protein_fat_deviation", nullable = false)
    private Long weightProteinFatDeviation = 8L; // w4: Cân bằng Đạm & Béo

    @Builder.Default
    @Column(name = "weight_fiber_bonus", nullable = false)
    private Long weightFiberBonus = 15L; // w5: Thưởng chất xơ làm chậm hấp thu đường

    @Builder.Default
    @Column(name = "weight_preference_bonus", nullable = false)
    private Long weightPreferenceBonus = 12L; // w6: Thưởng sở thích người dùng

    @Builder.Default
    @Column(name = "max_time_seconds", nullable = false)
    private Double maxTimeSeconds = 1.5;

    @Builder.Default
    @Column(name = "num_search_workers", nullable = false)
    private Integer numSearchWorkers = 2;

    @Builder.Default
    @Column(name = "is_default", nullable = false)
    private Boolean isDefault = false;
}
