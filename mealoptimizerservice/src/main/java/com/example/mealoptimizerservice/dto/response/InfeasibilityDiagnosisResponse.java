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
public class InfeasibilityDiagnosisResponse {
    private boolean isFeasibleUnderStandardRules;
    private List<String> detectedConflicts;
    private List<String> actionableRecommendations;
}
