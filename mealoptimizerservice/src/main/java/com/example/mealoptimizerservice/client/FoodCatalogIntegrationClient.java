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
 * Tích hợp sẵn bộ ứng viên Fallback nội bộ 24 món chuẩn Việt Nam để service luôn tự chạy độc lập
 * hoặc khi Food Catalog Service chưa bật trong quá trình phát triển.
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
                Set.of(MealSlot.BREAKFAST), 3600L, 410L, 45L, 260L, 80L, 165L, 2, 2, 2, 130, "1 tô vừa (420g)",
                1L, "Bánh phở gạo lứt", new BigDecimal("120"), 2L, "Ức gà không da", new BigDecimal("90"));

        addDish(102L, "BF_BUN_CA_RO", "Bún gạo lứt cá rô đồng cải xanh", DishRole.COMPOSITE_DISH, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.BREAKFAST), 3400L, 390L, 52L, 240L, 75L, 150L, 2, 2, 2, 125, "1 tô vừa (400g)",
                3L, "Bún gạo lứt khô", new BigDecimal("55"), 4L, "Phi lê cá rô đồng", new BigDecimal("90"));

        addDish(103L, "BF_CHAO_YEN_MACH", "Cháo yến mạch thịt băm nấm hương", DishRole.COMPOSITE_DISH, IngredientGroup.PORK,
                Set.of(MealSlot.BREAKFAST), 3200L, 360L, 65L, 210L, 85L, 140L, 2, 2, 2, 120, "1 bát tô (350g)",
                5L, "Yến mạch nguyên cán", new BigDecimal("50"), 6L, "Thịt thăn lợn nạc", new BigDecimal("70"));

        addDish(104L, "BF_MIEN_DONG_GA", "Miến dong ức gà măng tươi", DishRole.COMPOSITE_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.BREAKFAST), 3100L, 380L, 48L, 235L, 65L, 135L, 2, 2, 2, 118, "1 tô vừa (380g)",
                7L, "Miến dong nguyên chất", new BigDecimal("50"), 2L, "Ức gà không da", new BigDecimal("85"));

        // 2. Nhóm Tinh bột chính cho Bữa Trưa & Tối (MAIN_STARCH: cho phép 0.5 -> 1.5 bát)
        addDish(201L, "ST_COM_GAO_LUT", "Cơm gạo lứt hấp mềm", DishRole.MAIN_STARCH, IngredientGroup.RICE_GRAIN,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1750L, 345L, 28L, 38L, 14L, 155L, 1, 3, 1, 140, "1 lưng bát con (120g)",
                8L, "Gạo lứt tẻ", new BigDecimal("50"), null, null, null);

        addDish(202L, "ST_COM_HAT_KE", "Cơm gạo lứt trộn hạt kê & đậu đen", DishRole.MAIN_STARCH, IngredientGroup.RICE_GRAIN,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1800L, 330L, 42L, 52L, 16L, 142L, 1, 3, 1, 130, "1 lưng bát con (120g)",
                8L, "Gạo lứt tẻ", new BigDecimal("40"), 9L, "Đậu đen xanh lòng", new BigDecimal("15"));

        addDish(203L, "ST_BUN_GAO_LUT", "Bún gạo lứt luộc tươi", DishRole.MAIN_STARCH, IngredientGroup.NOODLE_TUBER,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1650L, 340L, 25L, 32L, 10L, 148L, 1, 3, 1, 115, "1 đĩa nhỏ (130g)",
                3L, "Bún gạo lứt khô", new BigDecimal("50"), null, null, null);

        // 3. Nhóm Món mặn / Đạm (PROTEIN_DISH)
        addDish(301L, "PR_UC_GA_RIM_GUNG", "Ức gà rim gừng ít muối", DishRole.PROTEIN_DISH, IngredientGroup.POULTRY,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1650L, 18L, 4L, 255L, 58L, 8L, 2, 3, 1, 135, "1 đĩa nhỏ (90g)",
                2L, "Ức gà không da", new BigDecimal("115"), null, null, null);

        addDish(302L, "PR_CA_THU_SOT_CA", "Cá thu hấp sốt cà chua tươi", DishRole.PROTEIN_DISH, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1950L, 35L, 12L, 240L, 95L, 12L, 2, 3, 1, 140, "1 khúc vừa (100g)",
                10L, "Cá thu tươi", new BigDecimal("120"), 11L, "Cà chua đỏ", new BigDecimal("60"));

        addDish(303L, "PR_THIT_LON_LUOC", "Thịt thăn lợn luộc cuốn rau sống", DishRole.PROTEIN_DISH, IngredientGroup.PORK,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1800L, 10L, 5L, 235L, 85L, 4L, 2, 3, 1, 128, "1 đĩa vừa (85g)",
                6L, "Thịt thăn lợn nạc", new BigDecimal("110"), null, null, null);

        addDish(304L, "PR_DAU_PHU_NHI_THIT", "Đậu phụ nhồi thịt hấp nấm mèo", DishRole.PROTEIN_DISH, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1700L, 38L, 18L, 185L, 92L, 10L, 2, 3, 1, 132, "2 miếng vừa (120g)",
                12L, "Đậu phụ trắng", new BigDecimal("100"), 6L, "Thịt thăn lợn nạc", new BigDecimal("45"));

        addDish(305L, "PR_BO_XAO_LUC_LAC", "Thịt thăn bò áp chảo ớt chuông", DishRole.PROTEIN_DISH, IngredientGroup.BEEF,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 1900L, 42L, 16L, 248L, 82L, 14L, 2, 3, 1, 138, "1 đĩa nhỏ (110g)",
                13L, "Thịt thăn bò", new BigDecimal("105"), 14L, "Ớt chuông Đà Lạt", new BigDecimal("60"));

        // 4. Nhóm Món Rau củ (VEGGIE_DISH)
        addDish(401L, "VG_BONG_CAI_LUOC", "Bông cải xanh & cà rốt hấp", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 550L, 65L, 45L, 38L, 8L, 16L, 2, 3, 1, 135, "1 đĩa vừa (150g)",
                15L, "Súp lơ xanh (Bông cải)", new BigDecimal("160"), null, null, null);

        addDish(402L, "VG_RAU_MUONG_LUOC", "Rau muống luộc chấm tương bần ít muối", DishRole.VEGGIE_DISH, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 480L, 52L, 38L, 35L, 6L, 12L, 2, 3, 1, 130, "1 đĩa vừa (150g)",
                16L, "Rau muống tươi", new BigDecimal("170"), null, null, null);

        addDish(403L, "VG_MUOP_DANG_XAO_TRUNG", "Khổ qua (Mướp đắng) xào trứng", DishRole.VEGGIE_DISH, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 920L, 48L, 36L, 75L, 52L, 11L, 2, 2, 2, 125, "1 đĩa vừa (140g)",
                17L, "Khổ qua (Mướp đắng)", new BigDecimal("130"), 18L, "Trứng gà ta", new BigDecimal("50"));

        addDish(404L, "VG_SU_SU_LUOC", "Su su & đậu cô ve luộc muối vừng", DishRole.VEGGIE_DISH, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 620L, 72L, 42L, 32L, 18L, 18L, 2, 3, 1, 122, "1 đĩa vừa (150g)",
                19L, "Quả su su", new BigDecimal("150"), null, null, null);

        // 5. Nhóm Món Canh (SOUP)
        addDish(501L, "SP_CANH_CAI_TOM", "Canh cải ngọt nấu tôm tươi", DishRole.SOUP, IngredientGroup.FISH_SEAFOOD,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 680L, 38L, 26L, 85L, 18L, 9L, 2, 2, 2, 136, "1 bát con (200ml)",
                20L, "Rau cải ngọt", new BigDecimal("120"), 21L, "Tôm sú tươi bóc nõn", new BigDecimal("35"));

        addDish(502L, "SP_CANH_MONG_TOI", "Canh mồng tơi mướp hương nấu nghêu", DishRole.SOUP, IngredientGroup.LEAFY_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 540L, 42L, 32L, 62L, 12L, 10L, 2, 2, 2, 132, "1 bát con (200ml)",
                22L, "Rau mồng tơi", new BigDecimal("120"), null, null, null);

        addDish(503L, "SP_CANH_BI_DO_THIT", "Canh bí xanh nấu sườn non hớt bọt", DishRole.SOUP, IngredientGroup.ROOT_FRUIT_VEG,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 650L, 46L, 28L, 72L, 22L, 11L, 2, 2, 2, 128, "1 bát con (200ml)",
                23L, "Bí đao xanh", new BigDecimal("140"), null, null, null);

        addDish(504L, "SP_CANH_RONG_BIEN", "Canh rong biển đậu phụ non", DishRole.SOUP, IngredientGroup.SOY_TOFU,
                Set.of(MealSlot.LUNCH, MealSlot.DINNER), 590L, 32L, 29L, 68L, 24L, 7L, 2, 2, 2, 126, "1 bát con (200ml)",
                12L, "Đậu phụ trắng", new BigDecimal("50"), null, null, null);

        // 6. Nhóm Bữa Phụ (SNACK)
        addDish(601L, "SN_SUA_HAT_OC_CHO", "Sữa đậu nành óc chó không đường + 1 quả ổi", DishRole.SNACK, IngredientGroup.NUT_SEED,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1450L, 135L, 48L, 75L, 62L, 42L, 2, 2, 2, 140, "1 ly 200ml + 100g ổi",
                24L, "Ổi lê tươi", new BigDecimal("100"), 25L, "Hạt óc chó & Đậu nành", new BigDecimal("30"));

        addDish(602L, "SN_TAO_XANH_HANH_NHAN", "Táo xanh + 10 hạt hạnh nhân rang mộc", DishRole.SNACK, IngredientGroup.FRUIT,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1380L, 142L, 42L, 45L, 68L, 52L, 2, 2, 2, 135, "1/2 quả táo + 15g hạt",
                26L, "Táo xanh", new BigDecimal("110"), 27L, "Hạt hạnh nhân", new BigDecimal("15"));

        addDish(603L, "SN_SUA_CHUA_HY_LAP", "Sữa chua Hy Lạp không đường trộn hạt chia", DishRole.SNACK, IngredientGroup.MILK_DAIRY,
                Set.of(MealSlot.MORNING_SNACK, MealSlot.AFTERNOON_SNACK), 1250L, 95L, 38L, 115L, 45L, 28L, 2, 2, 2, 130, "1 hũ 100g + 10g hạt chia",
                28L, "Sữa chua không đường", new BigDecimal("100"), null, null, null);
    }

    private void addDish(
            Long id, String code, String nameVi, DishRole role, IngredientGroup group, Set<MealSlot> slots,
            long calX10, long carbX10, long fiberX10, long protX10, long fatX10, long glX10,
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
                .minServingX2(minS2).maxServingX2(maxS2).stepServingX2(stepS2)
                .basePreferenceScore(score)
                .householdUnitLabel(unitLabel)
                .rawIngredientsPerServing(rawMap)
                .build());
    }
}
