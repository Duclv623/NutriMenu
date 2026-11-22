package com.example.mealoptimizerservice.dto.request;

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
public class RebalanceRemainingMealsRequest {
    @NotEmpty
    private Set<MealSlot> alreadyEatenSlots;
    @NotNull @DecimalMin("0.0")
    private BigDecimal consumedCaloriesKcal;
    @NotNull @DecimalMin("0.0")
    private BigDecimal consumedNetCarbG;
    @NotNull @DecimalMin("0.0")
    private BigDecimal consumedProteinG;
    @NotNull @DecimalMin("0.0")
    private BigDecimal consumedFatG;
}
