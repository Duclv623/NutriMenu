package com.example.mealoptimizerservice.dto.response;

import com.example.mealoptimizerservice.dto.MathematicalBreakdownDto;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MealPlanResponse {
    private Long planId;
    private Long userId;
    private LocalDate planDate;
    private SolverRunStatus solverStatus;
    private Long solveTimeMs;
    private BigDecimal targetCaloriesKcal;
    private BigDecimal actualCaloriesKcal;
    private BigDecimal targetNetCarbG;
    private BigDecimal actualNetCarbG;
    private BigDecimal actualFiberG;
    private BigDecimal targetProteinG;
    private BigDecimal actualProteinG;
    private BigDecimal targetFatG;
    private BigDecimal actualFatG;
    private BigDecimal actualTotalGl;
    private Integer userRating;
    private String userFeedback;
    private Map<MealSlot, List<MealPlanItemResponse>> mealsBySlot;
    private List<String> medicalWarnings;
    private MathematicalBreakdownDto mathBreakdown;

    public static MealPlanResponse fromEntity(MealPlan plan, MathematicalBreakdownDto math, List<String> warnings) {
        Map<MealSlot, List<MealPlanItemResponse>> grouped = new EnumMap<>(MealSlot.class);
        for (MealPlanItem item : plan.getItems()) {
            grouped.computeIfAbsent(item.getMealSlot(), k -> new ArrayList<>())
                    .add(MealPlanItemResponse.fromEntity(item));
        }
        return MealPlanResponse.builder()
                .planId(plan.getId())
                .userId(plan.getUserId())
                .planDate(plan.getPlanDate())
                .solverStatus(plan.getSolverStatus())
                .solveTimeMs(plan.getSolveTimeMs())
                .targetCaloriesKcal(plan.getTargetCaloriesKcal())
                .actualCaloriesKcal(plan.getActualCaloriesKcal())
                .targetNetCarbG(plan.getTargetNetCarbG())
                .actualNetCarbG(plan.getActualNetCarbG())
                .actualFiberG(plan.getActualFiberG())
                .targetProteinG(plan.getTargetProteinG())
                .actualProteinG(plan.getActualProteinG())
                .targetFatG(plan.getTargetFatG())
                .actualFatG(plan.getActualFatG())
                .actualTotalGl(plan.getActualTotalGl())
                .userRating(plan.getUserRating())
                .userFeedback(plan.getUserFeedback())
                .mealsBySlot(grouped)
                .medicalWarnings(warnings != null ? warnings : Collections.emptyList())
                .mathBreakdown(math)
                .build();
    }
}
