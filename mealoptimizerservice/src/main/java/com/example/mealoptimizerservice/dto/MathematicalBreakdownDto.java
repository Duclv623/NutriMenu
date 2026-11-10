package com.example.mealoptimizerservice.dto;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

// --- DTO Phản hồi Thực đơn & Giải trình Toán học CP-SAT ---
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MathematicalBreakdownDto {
    private SolverRunStatus solverStatus;
    private long solveTimeMs;
    private double objectiveValue;
    private int totalCandidatesEvaluated;
    private int totalDecisionVariables;
    private BigDecimal calOverKcal;
    private BigDecimal calUnderKcal;
    private BigDecimal carbOverG;
    private BigDecimal carbUnderG;
    private BigDecimal proteinOverG;
    private BigDecimal proteinUnderG;
    private BigDecimal fatOverG;
    private BigDecimal fatUnderG;
}
