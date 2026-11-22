package com.example.mealoptimizerservice.solver;

import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.dto.request.PatientProfileMealRequest;
import com.example.mealoptimizerservice.entity.MealSlotTemplate;
import com.example.mealoptimizerservice.entity.SolverWeightProfile;
import com.example.mealoptimizerservice.entity.enums.*;
import com.example.mealoptimizerservice.service.DiabeticClinicalTargetCalculator;
import com.google.ortools.Loader;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

class CpSatMealOptimizationEngineTest {

    @BeforeAll
    static void initNativeLibraries() {
        Loader.loadNativeLibraries();
    }

    @Test
    @DisplayName("Kiểm tra bộ tính chỉ tiêu lâm sàng cho bệnh nhân ĐTĐ típ 2")
    void testClinicalTargetCalculator() {
        DiabeticClinicalTargetCalculator calculator = new DiabeticClinicalTargetCalculator();
        PatientProfileMealRequest profile = new PatientProfileMealRequest();
        profile.setGender(Gender.MALE);
        profile.setHeightMeters(new BigDecimal("1.70"));
        profile.setActualWeightKg(new BigDecimal("72.0"));
        profile.setActivityLevel(PhysicalActivityLevel.LIGHT);
        profile.setHasHypertension(true);
        profile.setHasDyslipidemia(false);
        profile.setHasGout(false);
        profile.setHasChronicKidneyDisease(false);

        var targets = calculator.calculateTargets(profile);
        assertNotNull(targets);
        assertEquals(new BigDecimal("63.58"), targets.getIdealBodyWeightKg()); // 1.7^2 * 22 = 63.58
        assertTrue(targets.getTargetCaloriesKcal().compareTo(new BigDecimal("1200")) >= 0);
        assertTrue(targets.getMaxDailyGl().compareTo(new BigDecimal("80.0")) <= 0);
        assertTrue(targets.getAppliedExcludedTags().contains(MedicalTag.HIGH_SODIUM)); // do Tăng huyết áp
        System.out.println(">> Đích calo: " + targets.getTargetCaloriesKcal() + " kcal, CNLT: " + targets.getIdealBodyWeightKg() + " kg");
    }

    @Test
    @DisplayName("Kiểm tra Google OR-Tools CP-SAT sinh thực đơn 1 ngày chuẩn mâm cơm Việt")
    void testCpSatEngineMealGeneration() {
        CpSatMealOptimizationEngine engine = new CpSatMealOptimizationEngine();

        // 1. Tạo 4 MealSlotTemplate chuẩn
        List<MealSlotTemplate> slots = List.of(
                MealSlotTemplate.builder()
                        .mealSlot(MealSlot.BREAKFAST)
                        .calorieRatioPct(new BigDecimal("30.0"))
                        .minNetCarbG(new BigDecimal("30.0"))
                        .maxNetCarbG(new BigDecimal("68.0"))
                        .maxGl(new BigDecimal("24.0"))
                        .allowCompositeDish(true)
                        .build(),
                MealSlotTemplate.builder()
                        .mealSlot(MealSlot.LUNCH)
                        .calorieRatioPct(new BigDecimal("30.0"))
                        .minNetCarbG(new BigDecimal("30.0"))
                        .maxNetCarbG(new BigDecimal("68.0"))
                        .maxGl(new BigDecimal("24.0"))
                        .allowCompositeDish(false)
                        .reqMainStarch(1).reqProteinDish(1).reqVeggieDish(1).reqSoup(1).reqSnack(0)
                        .build(),
                MealSlotTemplate.builder()
                        .mealSlot(MealSlot.AFTERNOON_SNACK)
                        .calorieRatioPct(new BigDecimal("10.0"))
                        .minNetCarbG(new BigDecimal("8.0"))
                        .maxNetCarbG(new BigDecimal("25.0"))
                        .maxGl(new BigDecimal("8.0"))
                        .allowCompositeDish(false)
                        .reqMainStarch(0).reqProteinDish(0).reqVeggieDish(0).reqSoup(0).reqSnack(1)
                        .build(),
                MealSlotTemplate.builder()
                        .mealSlot(MealSlot.DINNER)
                        .calorieRatioPct(new BigDecimal("30.0"))
                        .minNetCarbG(new BigDecimal("30.0"))
                        .maxNetCarbG(new BigDecimal("68.0"))
                        .maxGl(new BigDecimal("24.0"))
                        .allowCompositeDish(false)
                        .reqMainStarch(1).reqProteinDish(1).reqVeggieDish(1).reqSoup(1).reqSnack(0)
                        .build()
        );

        // 2. Mock danh sách món ăn ứng viên đa dạng
        List<DishSolverDto> candidates = createSampleVietnameseDishes();

        // 3. Weight Profile
        SolverWeightProfile profile = SolverWeightProfile.builder()
                .code("STRICT_GLYCEMIC")
                .nameVi("Kiểm soát Đường huyết Nghiêm ngặt")
                .weightCarbDeviation(60L)
                .weightGlycemicLoad(35L)
                .weightCalorieDeviation(10L)
                .weightProteinFatDeviation(8L)
                .weightFiberBonus(18L)
                .weightPreferenceBonus(12L)
                .maxTimeSeconds(2.0)
                .numSearchWorkers(2)
                .build();

        CpSatMealOptimizationEngine.SolverInputContext context = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(new BigDecimal("1600.0"))
                .targetNetCarbG(new BigDecimal("220.0"))
                .targetProteinG(new BigDecimal("70.0"))
                .targetFatG(new BigDecimal("49.0"))
                .maxDailyGl(new BigDecimal("80.0"))
                .maxDailySodiumMg(new BigDecimal("2400.0"))
                .maxDailyCholesterolMg(new BigDecimal("300.0"))
                .minDailyFiberG(new BigDecimal("20.0"))
                .activeSlots(slots)
                .candidates(candidates)
                .weightProfile(profile)
                .enableRandomPerturbation(false)
                .build();

        var result = engine.solveOptimalMealPlan(context);

        assertNotNull(result);
        System.out.println(">> Trạng thái giải: " + result.getStatus());
        assertTrue(result.getStatus() == SolverRunStatus.OPTIMAL || result.getStatus() == SolverRunStatus.FEASIBLE,
                "Solver phải tìm được lời giải OPTIMAL hoặc FEASIBLE nhưng lại là " + result.getStatus());

        assertNotNull(result.getSelectedDishes());
        assertFalse(result.getSelectedDishes().isEmpty());
        System.out.println(">> Tổng số món được chọn: " + result.getSelectedDishes().size());

        double totalGl = 0;
        for (var item : result.getSelectedDishes()) {
            double serving = item.getServingScaledX2() / 2.0;
            double cal = (item.getDish().getCaloriesX10() / 10.0) * serving;
            double gl = (item.getDish().getGlX10() / 10.0) * serving;
            totalGl += gl;
            System.out.printf("   [%s] %s | Khẩu phần: %.1f | Calo: %.1f | GL: %.1f%n",
                    item.getMealSlot(),
                    item.getDish().getNameVi(),
                    serving,
                    cal,
                    gl
            );
        }

        System.out.printf(">> TỔNG GL TRONG NGÀY: %.2f (Trần cho phép <= 80.0)%n", totalGl);
        assertTrue(totalGl <= 80.05, "Tổng GL trong ngày phải <= 80.0");
    }

    private List<DishSolverDto> createSampleVietnameseDishes() {
        List<DishSolverDto> list = new ArrayList<>();
        long id = 1;

        // Bữa sáng: Composite Dish
        list.add(createDish(id++, "Phở gà gạo lứt", DishRole.COMPOSITE_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.BREAKFAST), 380, 45, 25, 8, 4, 17, 2, 2, 2));
        list.add(createDish(id++, "Bún bò Huế yến mạch", DishRole.COMPOSITE_DISH, IngredientGroup.BEEF,
                Set.of(MealSlot.BREAKFAST), 420, 48, 28, 12, 5, 20, 2, 2, 2));
        list.add(createDish(id++, "Cháo yến mạch ức gà", DishRole.COMPOSITE_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.BREAKFAST), 320, 40, 22, 6, 6, 14, 2, 2, 2));

        // Tinh bột: Main Starch (Trưa & Tối)
        list.add(createDish(id++, "Cơm gạo lứt huyết rồng", DishRole.MAIN_STARCH, IngredientGroup.RICE_GRAIN,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 210, 44, 4.5, 1.5, 3.5, 19, 1, 3, 1));
        list.add(createDish(id++, "Khoai lang hấp", DishRole.MAIN_STARCH, IngredientGroup.NOODLE_TUBER,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 160, 37, 2.0, 0.5, 4.0, 16, 1, 3, 1));
        list.add(createDish(id++, "Bún gạo lứt trộn", DishRole.MAIN_STARCH, IngredientGroup.NOODLE_TUBER,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 200, 42, 4.0, 1.0, 3.0, 17, 1, 3, 1));

        // Món đạm: Protein Dish (Trưa & Tối)
        list.add(createDish(id++, "Cá hồi áp chảo sốt chanh leo", DishRole.PROTEIN_DISH, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 220, 2, 24, 13, 0.5, 0.3, 1, 2, 1));
        list.add(createDish(id++, "Ức gà hấp lá chanh", DishRole.PROTEIN_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 165, 0, 31, 3.5, 0, 0, 1, 2, 1));
        list.add(createDish(id++, "Đậu phụ sốt cà chua ít muối", DishRole.PROTEIN_DISH, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 140, 6, 14, 8, 2, 1.5, 1, 3, 1));
        list.add(createDish(id++, "Thịt lợn nạc luộc chấm mắm nhạt", DishRole.PROTEIN_DISH, IngredientGroup.PORK,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 180, 0, 26, 7, 0, 0, 1, 2, 1));

        // Món rau: Veggie Dish (Trưa & Tối)
        list.add(createDish(id++, "Rau muống luộc", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 35, 3, 2.5, 0.4, 2.8, 0.5, 2, 4, 1));
        list.add(createDish(id++, "Bông cải xanh hấp", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 45, 5, 3.5, 0.5, 3.2, 0.7, 2, 4, 1));
        list.add(createDish(id++, "Rau củ luộc thập cẩm", DishRole.VEGGIE_DISH, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 50, 7, 2.0, 0.3, 3.0, 1.7, 2, 4, 1));

        // Món canh: Soup (Trưa & Tối)
        list.add(createDish(id++, "Canh cải ngọt nấu tôm", DishRole.SOUP, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 60, 3, 8, 1.2, 1.8, 0.5, 2, 2, 2));
        list.add(createDish(id++, "Canh bí xanh nấu thịt nạc", DishRole.SOUP, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 65, 4, 7, 1.5, 1.5, 0.8, 2, 2, 2));
        list.add(createDish(id++, "Canh rong biển đậu hũ", DishRole.SOUP, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 55, 3, 5, 2.0, 1.2, 0.4, 2, 2, 2));

        // Bữa phụ: Snack
        list.add(createDish(id++, "Sữa chua không đường hạt chia", DishRole.SNACK, IngredientGroup.MILK_DAIRY,
                Set.of(MealSlot.AFTERNOON_SNACK), 110, 10, 6, 4.5, 2.5, 2.5, 2, 2, 2));
        list.add(createDish(id++, "Táo ta tươi 1 quả nhỏ", DishRole.SNACK, IngredientGroup.FRUIT,
                Set.of(MealSlot.AFTERNOON_SNACK), 65, 14, 0.5, 0.3, 2.4, 5.0, 2, 2, 2));
        list.add(createDish(id++, "Hạnh nhân nướng mộc 10 hạt", DishRole.SNACK, IngredientGroup.NUT_SEED,
                Set.of(MealSlot.AFTERNOON_SNACK), 80, 2, 3, 7, 1.5, 0.2, 2, 2, 2));

        return list;
    }

    private DishSolverDto createDish(long id, String name, DishRole role, IngredientGroup group,
                                    Set<MealSlot> slots, double cal, double carb, double prot, double fat,
                                    double fiber, double gl, int minX2, int maxX2, int stepX2) {
        return DishSolverDto.builder()
                .dishId(id)
                .code("DISH_" + id)
                .nameVi(name)
                .role(role)
                .ingredientGroup(group)
                .validMealSlots(slots)
                .caloriesX10(Math.round(cal * 10))
                .netCarbX10(Math.round(carb * 10))
                .proteinX10(Math.round(prot * 10))
                .fatX10(Math.round(fat * 10))
                .fiberX10(Math.round(fiber * 10))
                .sodiumX10(1500L)
                .cholesterolX10(250L)
                .glX10(Math.round(gl * 10))
                .minServingX2(minX2)
                .maxServingX2(maxX2)
                .stepServingX2(stepX2)
                .basePreferenceScore(0)
                .householdUnitLabel("bát/đĩa")
                .rawIngredientsPerServing(Map.of())
                .build();
    }
}
