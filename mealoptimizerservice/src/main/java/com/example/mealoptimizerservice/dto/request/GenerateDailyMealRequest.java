package com.example.mealoptimizerservice.dto.request;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

// --- DTO Yêu cầu Tạo Thực đơn (User & Dry-Run) ---
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class GenerateDailyMealRequest {
    @NotNull
    private LocalDate planDate;

    @NotNull @DecimalMin("1000.0") @DecimalMax("3500.0")
    @Builder.Default
    private BigDecimal targetCaloriesKcal = new BigDecimal("1600.0");

    @NotNull @DecimalMin("80.0") @DecimalMax("300.0")
    @Builder.Default
    private BigDecimal targetNetCarbG = new BigDecimal("175.0");

    @NotNull @DecimalMin("40.0") @DecimalMax("200.0")
    @Builder.Default
    private BigDecimal targetProteinG = new BigDecimal("85.0");

    @NotNull @DecimalMin("25.0") @DecimalMax("120.0")
    @Builder.Default
    private BigDecimal targetFatG = new BigDecimal("50.0");

    @Builder.Default
    private BigDecimal maxGiAllowed = new BigDecimal("69.9");

    @Builder.Default
    private Set<MedicalTag> patientContraindications = new HashSet<>();

    @Builder.Default
    private String templateCode = "STANDARD_4_MEALS";

    private Long weightProfileId;

    @Builder.Default
    private boolean enableRandomPerturbation = true;
}
