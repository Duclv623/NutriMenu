package com.example.mealoptimizerservice.config;

import com.example.mealoptimizerservice.entity.MealSlotTemplate;
import com.example.mealoptimizerservice.entity.SolverWeightProfile;
import com.example.mealoptimizerservice.entity.enums.MealSlot;
import com.example.mealoptimizerservice.repository.MealSlotTemplateRepository;
import com.example.mealoptimizerservice.repository.SolverWeightProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.math.BigDecimal;
import java.util.List;

@Configuration
@RequiredArgsConstructor
public class OptimizerConfiguration {

    private final SolverWeightProfileRepository profileRepo;
    private final MealSlotTemplateRepository templateRepo;

    /**
     * BULKHEAD PATTERN CHO CP-SAT:
     * Cô lập số luồng giải C++ OR-Tools để không bao giờ làm nghẽn luồng HTTP của Tomcat.
     */
    @Bean(name = "cpSatSolverBulkheadExecutor")
    public ThreadPoolTaskExecutor cpSatSolverBulkheadExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("cpsat-worker-");
        executor.initialize();
        return executor;
    }

    @Bean
    public CommandLineRunner seedOptimizerDefaults() {
        return args -> {
            if (profileRepo.count() == 0) {
                profileRepo.saveAll(List.of(
                        SolverWeightProfile.builder()
                                .code("STRICT_GLYCEMIC")
                                .nameVi("Kiểm soát Đường huyết Nghiêm ngặt (Mặc định)")
                                .weightCarbDeviation(60L)
                                .weightGlycemicLoad(35L)
                                .weightCalorieDeviation(10L)
                                .weightProteinFatDeviation(8L)
                                .weightFiberBonus(18L)
                                .weightPreferenceBonus(12L)
                                .maxTimeSeconds(1.5)
                                .numSearchWorkers(2)
                                .isDefault(true)
                                .build(),
                        SolverWeightProfile.builder()
                                .code("WEIGHT_LOSS_DIABETIC")
                                .nameVi("Kiểm soát Cân nặng & Đường huyết")
                                .weightCarbDeviation(45L)
                                .weightGlycemicLoad(25L)
                                .weightCalorieDeviation(30L)
                                .weightProteinFatDeviation(15L)
                                .weightFiberBonus(20L)
                                .weightPreferenceBonus(10L)
                                .maxTimeSeconds(1.5)
                                .numSearchWorkers(2)
                                .isDefault(false)
                                .build()
                ));
            }

            if (templateRepo.count() == 0) {
                templateRepo.saveAll(List.of(
                        MealSlotTemplate.builder()
                                .templateCode("STANDARD_4_MEALS")
                                .mealSlot(MealSlot.BREAKFAST)
                                .calorieRatioPct(new BigDecimal("25.0"))
                                .minNetCarbG(new BigDecimal("25.0"))
                                .maxNetCarbG(new BigDecimal("50.0"))
                                .maxGl(new BigDecimal("19.0"))
                                .allowCompositeDish(true)
                                .build(),
                        MealSlotTemplate.builder()
                                .templateCode("STANDARD_4_MEALS")
                                .mealSlot(MealSlot.LUNCH)
                                .calorieRatioPct(new BigDecimal("35.0"))
                                .minNetCarbG(new BigDecimal("35.0"))
                                .maxNetCarbG(new BigDecimal("65.0"))
                                .maxGl(new BigDecimal("20.0"))
                                .allowCompositeDish(false)
                                .reqMainStarch(1).reqProteinDish(1).reqVeggieDish(1).reqSoup(1).reqSnack(0)
                                .build(),
                        MealSlotTemplate.builder()
                                .templateCode("STANDARD_4_MEALS")
                                .mealSlot(MealSlot.AFTERNOON_SNACK)
                                .calorieRatioPct(new BigDecimal("10.0"))
                                .minNetCarbG(new BigDecimal("5.0"))
                                .maxNetCarbG(new BigDecimal("25.0"))
                                .maxGl(new BigDecimal("10.0"))
                                .allowCompositeDish(false)
                                .reqMainStarch(0).reqProteinDish(0).reqVeggieDish(0).reqSoup(0).reqSnack(1)
                                .build(),
                        MealSlotTemplate.builder()
                                .templateCode("STANDARD_4_MEALS")
                                .mealSlot(MealSlot.DINNER)
                                .calorieRatioPct(new BigDecimal("30.0"))
                                .minNetCarbG(new BigDecimal("30.0"))
                                .maxNetCarbG(new BigDecimal("55.0"))
                                .maxGl(new BigDecimal("19.0"))
                                .allowCompositeDish(false)
                                .reqMainStarch(1).reqProteinDish(1).reqVeggieDish(1).reqSoup(1).reqSnack(0)
                                .build()
                ));
            }
        };
    }
}
