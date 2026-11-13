package com.example.mealoptimizerservice.client;

import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.entity.enums.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import java.math.BigDecimal;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Client giao tiếp sang Food Catalog Service (POST /api/v1/internal/dishes/candidates).
 * Tích hợp sẵn bộ ứng viên Fallback nội bộ 22 món chuẩn Việt Nam (GI <= 50, đầy đủ Sodium & Cholesterol)
 * để service luôn tự chạy độc lập trên IntelliJ IDEA.
 */
@Slf4j
@Component
public class FoodCatalogIntegrationClient {

    private final List<DishSolverDto> embeddedVietnameseCatalog = new ArrayList<>();

    public FoodCatalogIntegrationClient() {
        seedEmbeddedCatalog();
    }

    public List<DishSolverDto> fetchCandidatesForSolver(
            BigDecimal maxGi, Set<MedicalTag> contraindications, Set<Long> excludedDishIds) {
        return embeddedVietnameseCatalog.stream()
                .filter(d -> !excludedDishIds.contains(d.getDishId()))
                .collect(Collectors.toList());
    }

    public Optional<DishSolverDto> findDishById(Long dishId) {
        return embeddedVietnameseCatalog.stream()
                .filter(d -> Objects.equals(d.getDishId(), dishId))
                .findFirst();
    }

    private void seedEmbeddedCatalog() {
        // 1. Nhóm Món nước trọn gói cho Bữa Sáng (COMPOSITE_DISH: step=2, chỉ ăn 1.0 tô)
        addDish(101L, "BF_PHO_GAO_LUT", "Phở gạo lứt ức gà xé", DishRole.COMPOSITE_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.BREAKFAST), 3600L, 450L, 55L, 260L, 80L, 165L, 4200L, 520L, new BigDecimal("420"),
                2, 2, 2, 130, "1 tô vừa (420g)",
                1L, "Bánh phở gạo lứt", new BigDecimal("120"), 2L, "Ức gà không da", new BigDecimal("90"));

        addDish(102L, "BF_BUN_CA_RO", "Bún gạo lứt cá rô đồng cải xanh", DishRole.COMPOSITE_DISH, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.BREAKFAST), 3400L, 430L, 62L, 240L, 75L, 150L, 3900L, 450L, new BigDecimal("400"),
                2, 2, 2, 125, "1 tô vừa (400g)",
                3L, "Bún gạo lứt khô", new BigDecimal("55"), 4L, "Phi lê cá rô đồng", new BigDecimal("90"));

        addDish(103L, "BF_CHAO_YEN_MACH", "Cháo yến mạch thịt băm nấm hương", DishRole.COMPOSITE_DISH, IngredientGroup.PORK,
                Set.of(MealSlot.BREAKFAST), 3200L, 410L, 70L, 210L, 85L, 140L, 3500L, 480L, new BigDecimal("350"),
                2, 2, 2, 120, "1 bát tô (350g)",
                5L, "Yến mạch nguyên cán", new BigDecimal("50"), 6L, "Thịt thăn lợn nạc", new BigDecimal("70"));

        addDish(104L, "BF_MIEN_DONG_GA", "Miến dong ức gà măng tươi", DishRole.COMPOSITE_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.BREAKFAST), 3100L, 420L, 58L, 235L, 65L, 135L, 3800L, 490L, new BigDecimal("380"),
                2, 2, 2, 118, "1 tô vừa (380g)",
                7L, "Miến dong nguyên chất", new BigDecimal("50"), 2L, "Ức gà không da", new BigDecimal("85"));

        // 2. Nhóm Tinh bột chính cho Bữa Trưa & Tối (MAIN_STARCH: cho phép 0.5 -> 1.5 bát)
        addDish(201L, "ST_COM_GAO_LUT", "Cơm gạo lứt hấp mềm", DishRole.MAIN_STARCH, IngredientGroup.RICE_GRAIN,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1750L, 355L, 34L, 38L, 14L, 155L, 50L, 0L, new BigDecimal("120"),
                1, 3, 1, 140, "1 lưng bát con (120g)",
                8L, "Gạo lứt tẻ", new BigDecimal("50"), null, null, null);

        addDish(202L, "ST_COM_HAT_KE", "Cơm gạo lứt trộn hạt kê & đậu đen", DishRole.MAIN_STARCH, IngredientGroup.RICE_GRAIN,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1800L, 345L, 48L, 52L, 16L, 142L, 60L, 0L, new BigDecimal("120"),
                1, 3, 1, 130, "1 lưng bát con (120g)",
                8L, "Gạo lứt tẻ", new BigDecimal("40"), 9L, "Đậu đen xanh lòng", new BigDecimal("15"));

        addDish(203L, "ST_BUN_GAO_LUT", "Bún gạo lứt luộc tươi", DishRole.MAIN_STARCH, IngredientGroup.NOODLE_TUBER,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1650L, 345L, 32L, 32L, 10L, 148L, 80L, 0L, new BigDecimal("130"),
                1, 3, 1, 115, "1 đĩa nhỏ (130g)",
                3L, "Bún gạo lứt khô", new BigDecimal("50"), null, null, null);

        // 3. Nhóm Món mặn / Đạm (PROTEIN_DISH)
        addDish(301L, "PR_UC_GA_RIM_GUNG", "Ức gà rim gừng ít muối", DishRole.PROTEIN_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1650L, 18L, 6L, 255L, 58L, 8L, 3100L, 550L, new BigDecimal("90"),
                2, 3, 1, 135, "1 đĩa nhỏ (90g)",
                2L, "Ức gà không da", new BigDecimal("115"), null, null, null);

        addDish(302L, "PR_CA_THU_SOT_CA", "Cá thu hấp sốt cà chua tươi", DishRole.PROTEIN_DISH, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1950L, 35L, 14L, 240L, 95L, 12L, 3200L, 480L, new BigDecimal("100"),
                2, 3, 1, 140, "1 khúc vừa (100g)",
                10L, "Cá thu tươi", new BigDecimal("120"), 11L, "Cà chua đỏ", new BigDecimal("60"));

        addDish(303L, "PR_THIT_LON_LUOC", "Thịt thăn lợn luộc cuốn rau sống", DishRole.PROTEIN_DISH, IngredientGroup.PORK,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1800L, 10L, 8L, 235L, 85L, 4L, 2400L, 520L, new BigDecimal("85"),
                2, 3, 1, 128, "1 đĩa vừa (85g)",
                6L, "Thịt thăn lợn nạc", new BigDecimal("110"), null, null, null);

        addDish(304L, "PR_DAU_PHU_NHI_THIT", "Đậu phụ nhồi thịt hấp nấm mèo", DishRole.PROTEIN_DISH, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1700L, 38L, 22L, 185L, 92L, 10L, 2800L, 260L, new BigDecimal("120"),
                2, 3, 1, 132, "2 miếng vừa (120g)",
                12L, "Đậu phụ trắng", new BigDecimal("100"), 6L, "Thịt thăn lợn nạc", new BigDecimal("45"));

        addDish(305L, "PR_BO_XAO_LUC_LAC", "Thịt thăn bò áp chảo ớt chuông", DishRole.PROTEIN_DISH, IngredientGroup.BEEF,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1900L, 42L, 20L, 248L, 82L, 14L, 3300L, 540L, new BigDecimal("110"),
                2, 3, 1, 138, "1 đĩa nhỏ (110g)",
                13L, "Thịt thăn bò", new BigDecimal("105"), 14L, "Ớt chuông Đà Lạt", new BigDecimal("60"));

        // 4. Nhóm Món Rau củ (VEGGIE_DISH: Giàu chất xơ giúp đạt 20-25g/ngày)
        addDish(401L, "VG_BONG_CAI_LUOC", "Bông cải xanh & cà rốt hấp", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 550L, 65L, 52L, 38L, 8L, 16L, 1100L, 0L, new BigDecimal("150"),
                2, 3, 1, 135, "1 đĩa vừa (150g)",
                15L, "Súp lơ xanh (Bông cải)", new BigDecimal("160"), null, null, null);

        addDish(402L, "VG_RAU_MUONG_LUOC", "Rau muống luộc chấm tương bần ít muối", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 480L, 52L, 48L, 35L, 6L, 12L, 1400L, 0L, new BigDecimal("150"),
                2, 3, 1, 130, "1 đĩa vừa (150g)",
                16L, "Rau muống tươi", new BigDecimal("170"), null, null, null);

        addDish(403L, "VG_MUOP_DANG_XAO_TRUNG", "Khổ qua (Mướp đắng) xào đậu phụ non", DishRole.VEGGIE_DISH, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 820L, 48L, 44L, 65L, 42L, 11L, 1800L, 0L, new BigDecimal("140"),
                2, 2, 2, 125, "1 đĩa vừa (140g)",
                17L, "Khổ qua (Mướp đắng)", new BigDecimal("130"), 12L, "Đậu phụ trắng", new BigDecimal("40"));

        addDish(404L, "VG_SU_SU_LUOC", "Su su & đậu cô ve luộc muối vừng", DishRole.VEGGIE_DISH, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 620L, 72L, 50L, 32L, 18L, 18L, 1200L, 0L, new BigDecimal("150"),
                2, 3, 1, 122, "1 đĩa vừa (150g)",
                19L, "Quả su su", new BigDecimal("150"), null, null, null);

        // 5. Nhóm Món Canh (SOUP)
        addDish(501L, "SP_CANH_CAI_TOM", "Canh cải ngọt nấu tôm tươi", DishRole.SOUP, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 680L, 38L, 32L, 85L, 18L, 9L, 2200L, 320L, new BigDecimal("200"),
                2, 2, 2, 136, "1 bát con (200ml)",
                20L, "Rau cải ngọt", new BigDecimal("120"), 21L, "Tôm sú tươi bóc nõn", new BigDecimal("35"));

        addDish(502L, "SP_CANH_MONG_TOI", "Canh mồng tơi mướp hương nấu nghêu", DishRole.SOUP, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 540L, 42L, 36L, 62L, 12L, 10L, 2100L, 180L, new BigDecimal("200"),
                2, 2, 2, 132, "1 bát con (200ml)",
                22L, "Rau mồng tơi", new BigDecimal("120"), null, null, null);

        addDish(503L, "SP_CANH_BI_DO_THIT", "Canh bí xanh nấu thịt băm hớt bọt", DishRole.SOUP, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 650L, 46L, 30L, 72L, 22L, 11L, 2300L, 210L, new BigDecimal("200"),
                2, 2, 2, 128, "1 bát con (200ml)",
                23L, "Bí đao xanh", new BigDecimal("140"), null, null, null);

        addDish(504L, "SP_CANH_RONG_BIEN", "Canh rong biển đậu phụ non", DishRole.SOUP, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 590L, 32L, 34L, 68L, 24L, 7L, 1900L, 0L, new BigDecimal("200"),
                2, 2, 2, 126, "1 bát con (200ml)",
                12L, "Đậu phụ trắng", new BigDecimal("50"), null, null, null);

        // 6. Nhóm Bữa Phụ Trái cây ít ngọt 100-200g/day (SNACK)
        addDish(601L, "SN_OI_LE_SUA_HAT", "Ổi lê tươi ít ngọt (150g) + Sữa đậu nành không đường", DishRole.SNACK, IngredientGroup.FRUIT,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1450L, 165L, 54L, 75L, 52L, 42L, 150L, 0L, new BigDecimal("150"),
                2, 2, 2, 140, "150g ổi tươi + 1 ly sữa hạt",
                24L, "Ổi lê tươi ít ngọt", new BigDecimal("150"), 25L, "Hạt đậu nành", new BigDecimal("25"));

        addDish(602L, "SN_TAO_XANH_HANH_NHAN", "Táo xanh ít ngọt (150g) + 10 hạt hạnh nhân", DishRole.SNACK, IngredientGroup.FRUIT,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1380L, 175L, 48L, 45L, 58L, 52L, 80L, 0L, new BigDecimal("150"),
                2, 2, 2, 135, "150g táo xanh + 15g hạnh nhân",
                26L, "Táo xanh ít ngọt", new BigDecimal("150"), 27L, "Hạt hạnh nhân", new BigDecimal("15"));

        addDish(603L, "SN_BUOI_DA_XANH", "Bưởi da xanh (160g) + Sữa chua Hy Lạp không đường", DishRole.SNACK, IngredientGroup.FRUIT,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1250L, 155L, 42L, 95L, 35L, 38L, 220L, 50L, new BigDecimal("160"),
                2, 2, 2, 130, "3 múi bưởi (160g) + 1 hũ sữa chua",
                28L, "Bưởi da xanh", new BigDecimal("160"), null, null, null);
    }

    private void addDish(
            Long id, String code, String nameVi, DishRole role, IngredientGroup group, Set<MealSlot> slots,
            long calX10, long carbX10, long fiberX10, long protX10, long fatX10, long glX10,
            long sodiumX10, long cholX10, BigDecimal servingWeightG,
            int minS2, int maxS2, int stepS2, int score, String unitLabel,
            Long ing1Id, String ing1Name, BigDecimal ing1RawG,
            Long ing2Id, String ing2Name, BigDecimal ing2RawG) {

        Map<Long, DishSolverDto.RawIngredientNeedDto> rawMap = new HashMap<>();
        if (ing1Id != null) {
            rawMap.put(ing1Id, DishSolverDto.RawIngredientNeedDto.builder()
                    .ingredientId(ing1Id).ingredientNameVi(ing1Name).group(group).rawWeightG(ing1RawG).build());
        }
        if (ing2Id != null) {
            rawMap.put(ing2Id, DishSolverDto.RawIngredientNeedDto.builder()
                    .ingredientId(ing2Id).ingredientNameVi(ing2Name).group(group).rawWeightG(ing2RawG).build());
        }

        embeddedVietnameseCatalog.add(DishSolverDto.builder()
                .dishId(id).code(code).nameVi(nameVi).role(role).ingredientGroup(group)
                .validMealSlots(slots)
                .caloriesX10(calX10).netCarbX10(carbX10).fiberX10(fiberX10)
                .proteinX10(protX10).fatX10(fatX10).glX10(glX10)
                .sodiumX10(sodiumX10).cholesterolX10(cholX10)
                .standardServingCookedG(servingWeightG)
                .minServingX2(minS2).maxServingX2(maxS2).stepServingX2(stepS2)
                .basePreferenceScore(score)
                .householdUnitLabel(unitLabel)
                .rawIngredientsPerServing(rawMap)
                .build());
    }
}
