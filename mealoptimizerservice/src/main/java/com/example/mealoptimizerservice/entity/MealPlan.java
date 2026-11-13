package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: MealPlan.java ---
@Entity
@Table(name = "meal_plans", indexes = {
        @Index(name = "idx_mp_user_date", columnList = "user_id, plan_date")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MealPlan {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "plan_date", nullable = false)
    private LocalDate planDate;

    @Column(name = "target_calories_kcal", nullable = false, precision = 7, scale = 2)
    private BigDecimal targetCaloriesKcal;

    @Column(name = "target_net_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal targetNetCarbG;

    @Column(name = "target_protein_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal targetProteinG;

    @Column(name = "target_fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal targetFatG;

    // Tổng dinh dưỡng thực tế (Nutritional Snapshot bất biến)
    @Builder.Default
    @Column(name = "actual_calories_kcal", nullable = false, precision = 7, scale = 2)
    private BigDecimal actualCaloriesKcal = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_net_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal actualNetCarbG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_fiber_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal actualFiberG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_protein_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal actualProteinG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal actualFatG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_total_gl", nullable = false, precision = 6, scale = 2)
    private BigDecimal actualTotalGl = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_sodium_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal actualSodiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "actual_cholesterol_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal actualCholesterolMg = BigDecimal.ZERO;

    @Enumerated(EnumType.STRING)
    @Column(name = "solver_status", nullable = false, length = 30)
    private SolverRunStatus solverStatus;

    @Column(name = "solve_time_ms")
    private Long solveTimeMs;

    @Column(name = "user_rating")
    private Integer userRating;

    @Column(name = "user_feedback", length = 500)
    private String userFeedback;

    @Builder.Default
    @OneToMany(mappedBy = "mealPlan", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.EAGER)
    private List<MealPlanItem> items = new ArrayList<>();

    @Builder.Default
    @Column(name = "created_at")
    private LocalDateTime createdAt = LocalDateTime.now();

    public void recalculateTotalsFromItems() {
        BigDecimal cal = BigDecimal.ZERO;
        BigDecimal carb = BigDecimal.ZERO;
        BigDecimal fiber = BigDecimal.ZERO;
        BigDecimal prot = BigDecimal.ZERO;
        BigDecimal fat = BigDecimal.ZERO;
        BigDecimal gl = BigDecimal.ZERO;
        BigDecimal sodium = BigDecimal.ZERO;
        BigDecimal chol = BigDecimal.ZERO;

        for (MealPlanItem item : items) {
            if (item.getStatus() != MealItemStatus.SKIPPED) {
                cal = cal.add(item.getSnapshotCaloriesKcal());
                carb = carb.add(item.getSnapshotNetCarbG());
                fiber = fiber.add(item.getSnapshotFiberG());
                prot = prot.add(item.getSnapshotProteinG());
                fat = fat.add(item.getSnapshotFatG());
                gl = gl.add(item.getSnapshotGl());
                sodium = sodium.add(item.getSnapshotSodiumMg() != null ? item.getSnapshotSodiumMg() : BigDecimal.ZERO);
                chol = chol.add(item.getSnapshotCholesterolMg() != null ? item.getSnapshotCholesterolMg() : BigDecimal.ZERO);
            }
        }
        this.actualCaloriesKcal = cal;
        this.actualNetCarbG = carb;
        this.actualFiberG = fiber;
        this.actualProteinG = prot;
        this.actualFatG = fat;
        this.actualTotalGl = gl;
        this.actualSodiumMg = sodium;
        this.actualCholesterolMg = chol;
    }
}
