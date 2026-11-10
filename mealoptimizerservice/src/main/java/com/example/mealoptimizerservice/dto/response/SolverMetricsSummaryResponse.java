package com.example.mealoptimizerservice.dto.response;

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
public class SolverMetricsSummaryResponse {
    private long totalRuns;
    private long optimalCount;
    private long feasibleCount;
    private long infeasibleCount;
    private double successRatePct;
    private double avgSolveTimeMs;
    private int activeSolverThreads;
    private int queuedSolverTasks;
}
