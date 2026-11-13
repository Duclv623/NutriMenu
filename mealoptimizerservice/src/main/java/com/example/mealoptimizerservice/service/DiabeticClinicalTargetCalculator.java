package com.example.mealoptimizerservice.service;

import com.example.mealoptimizerservice.client.FoodCatalogIntegrationClient;
import com.example.mealoptimizerservice.dto.*;
import com.example.mealoptimizerservice.dto.request.PatientProfileMealRequest.ComputedClinicalTargetsDto;
import com.example.mealoptimizerservice.entity.*;
import com.example.mealoptimizerservice.entity.enums.*;
import com.example.mealoptimizerservice.exception.OptimizerBusinessException;
import com.example.mealoptimizerservice.exception.ResourceNotFoundException;
import com.example.mealoptimizerservice.repository.*;
import com.example.mealoptimizerservice.solver.CpSatMealOptimizationEngine;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import com.example.mealoptimizerservice.dto.request.*;
import com.example.mealoptimizerservice.dto.response.*;

// --- FILE MỚI: DiabeticClinicalTargetCalculator.java ---
@Component
public class DiabeticClinicalTargetCalculator {

    /**
     * Tính toán toàn bộ chỉ tiêu dinh dưỡng trong ngày từ Hồ sơ người bệnh ĐTĐ típ 2:
     * 1. CNLT Nam = cao(m)^2 * 22 | CNLT Nữ = cao(m)^2 * 21
     * 2. Năng lượng = CNLT * (25 | 30 | 35 | 40 kcal) + Hiệu chỉnh Gầy / Béo phì
     * 3. Glucid: 50-60% (lấy đích 55%), Protein: 15-20% (đích 17.5%), Lipid: 20-30% (đích 27.5%)
     * 4. GI <= 50, GL <= 80/ngày, Cholesterol < 300mg (hoặc < 200mg nếu rối loạn mỡ máu),
     *    Natri < 2400mg/ngày, Chất xơ 20-25g/ngày.
     */
    public ComputedClinicalTargetsDto calculateTargets(PatientProfileMealRequest profile) {
        BigDecimal heightSquared = profile.getHeightMeters().multiply(profile.getHeightMeters());

        // 1. Tính Cân nặng lý tưởng (CNLT)
        BigDecimal cnltKg = heightSquared.multiply(profile.getGender().getIbwCoefficient())
                .setScale(2, RoundingMode.HALF_UP);

        // 2. Tính BMI thực tế để kiểm soát cân nặng cho người Gầy / Béo phì
        BigDecimal bmi = profile.getActualWeightKg()
                .divide(heightSquared, 2, RoundingMode.HALF_UP);

        // 3. Năng lượng cơ sở theo mức độ lao động và CNLT
        BigDecimal baseKcal = cnltKg.multiply(profile.getActivityLevel().getKcalPerKgIbw())
                .setScale(0, RoundingMode.HALF_UP);

        BigDecimal adjustedKcal = baseKcal;
        String weightStatus;

        if (bmi.compareTo(new BigDecimal("25.0")) >= 0) {
            weightStatus = "Béo phì (BMI >= 25) - Đã giảm trừ 300 kcal để kiểm soát cân nặng";
            adjustedKcal = baseKcal.subtract(new BigDecimal("300.0")).max(new BigDecimal("1200.0"));
        } else if (bmi.compareTo(new BigDecimal("23.0")) >= 0) {
            weightStatus = "Thừa cân (23 <= BMI < 25) - Đã giảm trừ 150 kcal để đưa về CNLT";
            adjustedKcal = baseKcal.subtract(new BigDecimal("150.0")).max(new BigDecimal("1200.0"));
        } else if (bmi.compareTo(new BigDecimal("18.5")) < 0) {
            weightStatus = "Thể trạng Gầy (BMI < 18.5) - Đã cộng thêm 250 kcal để phục hồi cân nặng";
            adjustedKcal = baseKcal.add(new BigDecimal("250.0"));
        } else {
            weightStatus = "Cân nặng Chuẩn lý tưởng (18.5 <= BMI < 23)";
        }

        // 4. Tính định lượng Glucid (50-60%, lấy trung tâm 55%), Protein (15-20%, lấy 17.5%), Lipid (20-30%, lấy 27.5%)
        BigDecimal carbRatio = new BigDecimal("0.55");
        BigDecimal protRatio = profile.isHasChronicKidneyDisease() ? new BigDecimal("0.15") : new BigDecimal("0.175");
        BigDecimal fatRatio = BigDecimal.ONE.subtract(carbRatio).subtract(protRatio);

        BigDecimal targetCarbG = adjustedKcal.multiply(carbRatio).divide(new BigDecimal("4.0"), 1, RoundingMode.HALF_UP);
        BigDecimal minCarbG = adjustedKcal.multiply(new BigDecimal("0.50")).divide(new BigDecimal("4.0"), 1, RoundingMode.HALF_UP);
        BigDecimal maxCarbG = adjustedKcal.multiply(new BigDecimal("0.60")).divide(new BigDecimal("4.0"), 1, RoundingMode.HALF_UP);

        BigDecimal targetProtG = adjustedKcal.multiply(protRatio).divide(new BigDecimal("4.0"), 1, RoundingMode.HALF_UP);
        BigDecimal targetFatG = adjustedKcal.multiply(fatRatio).divide(new BigDecimal("9.0"), 1, RoundingMode.HALF_UP);

        // 5. Giới hạn Cholesterol: < 200mg/ngày (nếu rối loạn mỡ máu) hoặc < 300mg/ngày (bình thường)
        BigDecimal maxCholesterolMg = profile.isHasDyslipidemia()
                ? new BigDecimal("200.0") : new BigDecimal("300.0");

        // 6. Tập hợp các nhãn cấm theo bệnh lý nền
        Set<MedicalTag> excludedTags = new HashSet<>();
        excludedTags.add(MedicalTag.HIGH_GI);
        excludedTags.add(MedicalTag.HIGH_GL);
        if (profile.isHasHypertension()) excludedTags.add(MedicalTag.HIGH_SODIUM);
        if (profile.isHasDyslipidemia()) excludedTags.add(MedicalTag.HIGH_SATURATED_FAT);
        if (profile.isHasGout()) excludedTags.add(MedicalTag.HIGH_PURINE);
        if (profile.isHasChronicKidneyDisease()) excludedTags.add(MedicalTag.HIGH_POTASSIUM);
        if (profile.getAdditionalAllergens() != null) excludedTags.addAll(profile.getAdditionalAllergens());

        return ComputedClinicalTargetsDto.builder()
                .idealBodyWeightKg(cnltKg)
                .actualBmi(bmi)
                .bodyWeightStatusVi(weightStatus)
                .baseEnergyKcal(baseKcal)
                .targetCaloriesKcal(adjustedKcal)
                .targetGlucidG(targetCarbG)
                .minGlucidG(minCarbG)
                .maxGlucidG(maxCarbG)
                .targetProteinG(targetProtG)
                .targetLipidG(targetFatG)
                .maxGiAllowed(new BigDecimal("50.0"))         // Chọn thực phẩm GI <= 50
                .maxDailyGl(new BigDecimal("80.0"))           // Đảm bảo GL <= 80/ngày
                .maxDailyCholesterolMg(maxCholesterolMg)      // < 200mg hoặc < 300mg
                .maxDailySodiumMg(new BigDecimal("2400.0"))   // Natri < 2400mg/ngày (6g muối)
                .minDailyFiberG(new BigDecimal("20.0"))       // Chất xơ tối thiểu 20g/ngày
                .targetDailyFiberG(new BigDecimal("25.0"))    // Đích chất xơ 25g/ngày
                .appliedExcludedTags(excludedTags)
                .build();
    }

    public GenerateDailyMealRequest toDailyMealRequest(
            PatientProfileMealRequest profile, ComputedClinicalTargetsDto targets) {
        return GenerateDailyMealRequest.builder()
                .planDate(profile.getPlanDate())
                .targetCaloriesKcal(targets.getTargetCaloriesKcal())
                .targetNetCarbG(targets.getTargetGlucidG())
                .targetProteinG(targets.getTargetProteinG())
                .targetFatG(targets.getTargetLipidG())
                .maxGiAllowed(targets.getMaxGiAllowed())
                .maxDailyGl(targets.getMaxDailyGl())
                .maxDailyCholesterolMg(targets.getMaxDailyCholesterolMg())
                .maxDailySodiumMg(targets.getMaxDailySodiumMg())
                .minDailyFiberG(targets.getMinDailyFiberG())
                .patientContraindications(targets.getAppliedExcludedTags())
                .templateCode("STANDARD_4_MEALS")
                .enableRandomPerturbation(true)
                .build();
    }
}
