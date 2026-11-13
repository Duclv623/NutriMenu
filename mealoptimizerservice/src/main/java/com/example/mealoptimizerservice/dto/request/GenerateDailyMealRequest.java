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

    @NotNull @DecimalMin("80.0") @DecimalMax("350.0")
    @Builder.Default
    private BigDecimal targetNetCarbG = new BigDecimal("220.0"); // 55% của 1600 kcal

    @NotNull @DecimalMin("35.0") @DecimalMax("200.0")
    @Builder.Default
    private BigDecimal targetProteinG = new BigDecimal("70.0"); // 17.5% của 1600 kcal

    @NotNull @DecimalMin("20.0") @DecimalMax("120.0")
    @Builder.Default
    private BigDecimal targetFatG = new BigDecimal("48.9");     // 27.5% của 1600 kcal

    @Builder.Default
    private BigDecimal maxGiAllowed = new BigDecimal("50.0");   // Chọn thực phẩm GI <= 50

    @Builder.Default
    private BigDecimal maxDailyGl = new BigDecimal("80.0");     // Ràng buộc GL <= 80/ngày

    @Builder.Default
    private BigDecimal maxDailySodiumMg = new BigDecimal("2400.0"); // Natri < 2400mg/ngày (6g muối)

    @Builder.Default
    private BigDecimal maxDailyCholesterolMg = new BigDecimal("300.0"); // < 300mg (hoặc < 200mg nếu mỡ máu)

    @Builder.Default
    private BigDecimal minDailyFiberG = new BigDecimal("20.0"); // Chất xơ 20-25g/ngày

    @Builder.Default
    private Set<MedicalTag> patientContraindications = new HashSet<>();

    @Builder.Default
    private String templateCode = "STANDARD_4_MEALS";

    private Long weightProfileId;

    @Builder.Default
    private boolean enableRandomPerturbation = true;
}
