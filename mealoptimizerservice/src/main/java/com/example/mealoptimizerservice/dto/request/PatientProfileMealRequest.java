package com.example.mealoptimizerservice.dto.request;

import com.example.mealoptimizerservice.entity.MealPlan;
import com.example.mealoptimizerservice.entity.MealPlanItem;
import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.validation.constraints.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

// --- FILE MỚI: PatientProfileMealRequest.java (Nhận Hồ sơ Bệnh nhân -> Tính Target -> Gợi ý) ---
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PatientProfileMealRequest {

    @NotNull
    private LocalDate planDate;

    @NotNull
    private Gender gender; // MALE (x22) hoặc FEMALE (x21)

    @NotNull
    @DecimalMin("1.20") @DecimalMax("2.20")
    private BigDecimal heightMeters; // Chiều cao tính bằng mét (VD: 1.65)

    @NotNull
    @DecimalMin("30.0") @DecimalMax("200.0")
    private BigDecimal actualWeightKg; // Cân nặng thực tế (kg) để kiểm tra Gầy / Béo phì

    @NotNull
    private PhysicalActivityLevel activityLevel; // BEDRIDDEN(25), LIGHT(30), MODERATE(35), HEAVY(40)

    // Các bệnh lý nền đi kèm
    @Builder.Default
    private boolean hasDyslipidemia = false; // Rối loạn mỡ máu -> Cholesterol < 200mg/day

    @Builder.Default
    private boolean hasHypertension = false; // Tăng huyết áp -> Lọc HIGH_SODIUM & Natri < 2400mg

    @Builder.Default
    private boolean hasGout = false; // Gout -> Lọc HIGH_PURINE

    @Builder.Default
    private boolean hasChronicKidneyDisease = false; // Suy thận -> Lọc HIGH_POTASSIUM & giảm đạm

    @Builder.Default
    private Set<MedicalTag> additionalAllergens = new HashSet<>();

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class ComputedClinicalTargetsDto {
        private BigDecimal idealBodyWeightKg;     // CNLT (kg)
        private BigDecimal actualBmi;             // BMI thực tế
        private String bodyWeightStatusVi;        // Gầy / Bình thường / Thừa cân - Béo phì
        private BigDecimal baseEnergyKcal;        // Năng lượng trước hiệu chỉnh cân nặng
        private BigDecimal targetCaloriesKcal;    // Năng lượng khẩu phần sau hiệu chỉnh
        private BigDecimal targetGlucidG;         // 55% tổng năng lượng (trong khoảng 50-60%)
        private BigDecimal minGlucidG;            // 50% tổng năng lượng
        private BigDecimal maxGlucidG;            // 60% tổng năng lượng
        private BigDecimal targetProteinG;        // 17.5% tổng năng lượng (trong khoảng 15-20%)
        private BigDecimal targetLipidG;          // 27.5% tổng năng lượng (trong khoảng 20-30%)
        private BigDecimal maxGiAllowed;          // <= 50.0
        private BigDecimal maxDailyGl;            // <= 80.0 / ngày
        private BigDecimal maxDailyCholesterolMg; // < 200mg (có mỡ máu) hoặc < 300mg (không mỡ máu)
        private BigDecimal maxDailySodiumMg;      // < 2400mg / ngày (6g muối)
        private BigDecimal minDailyFiberG;        // 20g / ngày
        private BigDecimal targetDailyFiberG;     // 25g / ngày
        private Set<MedicalTag> appliedExcludedTags;
    }
}
