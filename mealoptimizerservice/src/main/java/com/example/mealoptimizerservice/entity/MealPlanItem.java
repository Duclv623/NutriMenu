package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: MealPlanItem.java ---
@Entity
@Table(name = "meal_plan_items")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MealPlanItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meal_plan_id", nullable = false)
    private MealPlan mealPlan;

    @Enumerated(EnumType.STRING)
    @Column(name = "meal_slot", nullable = false, length = 30)
    private MealSlot mealSlot;

    @Column(name = "dish_id", nullable = false)
    private Long dishId;

    @Column(name = "dish_code", nullable = false, length = 50)
    private String dishCode;

    @Column(name = "dish_name_vi", nullable = false, length = 200)
    private String dishNameVi;

    @Enumerated(EnumType.STRING)
    @Column(name = "dish_role", nullable = false, length = 30)
    private DishRole dishRole;

    @Enumerated(EnumType.STRING)
    @Column(name = "ingredient_group", nullable = false, length = 30)
    private IngredientGroup ingredientGroup;

    // Bội số khẩu phần nguyên x2 (1 = 0.5 khẩu phần, 2 = 1.0 khẩu phần, 3 = 1.5 khẩu phần)
    @Column(name = "serving_scaled_x2", nullable = false)
    private Integer servingScaledX2;

    @Column(name = "serving_multiplier", nullable = false, precision = 4, scale = 2)
    private BigDecimal servingMultiplier;

    @Column(name = "household_unit_display", length = 150)
    private String householdUnitDisplay;

    // SNAPSHOT DINH DƯỠNG BẤT BIẾN TẠI THỜI ĐIỂM TẠO THỰC ĐƠN
    @Column(name = "snapshot_calories_kcal", nullable = false, precision = 7, scale = 2)
    private BigDecimal snapshotCaloriesKcal;

    @Column(name = "snapshot_net_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal snapshotNetCarbG;

    @Column(name = "snapshot_fiber_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal snapshotFiberG;

    @Column(name = "snapshot_protein_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal snapshotProteinG;

    @Column(name = "snapshot_fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal snapshotFatG;

    @Column(name = "snapshot_gl", nullable = false, precision = 5, scale = 2)
    private BigDecimal snapshotGl;

    @Builder.Default
    @Column(name = "snapshot_sodium_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal snapshotSodiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "snapshot_cholesterol_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal snapshotCholesterolMg = BigDecimal.ZERO;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private MealItemStatus status = MealItemStatus.PLANNED;

    @Builder.Default
    @Column(name = "is_locked", nullable = false)
    private Boolean isLocked = false;
}
