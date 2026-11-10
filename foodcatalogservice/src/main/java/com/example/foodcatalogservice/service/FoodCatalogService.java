package com.example.foodcatalogservice.service;

import com.example.foodcatalogservice.dto.DishSolverDto;
import com.example.foodcatalogservice.dto.RecipeIngredientBreakdownDto;
import com.example.foodcatalogservice.dto.request.*;
import com.example.foodcatalogservice.dto.response.*;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.*;
import com.example.foodcatalogservice.exception.BusinessRuleException;
import com.example.foodcatalogservice.exception.ResourceNotFoundException;
import com.example.foodcatalogservice.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class FoodCatalogService {

    private final DishRepository dishRepository;
    private final IngredientRepository ingredientRepository;
    private final DishIngredientRepository dishIngredientRepository;
    private final YieldFactorRepository yieldFactorRepository;
    private final UserFoodPreferenceRepository preferenceRepository;
    private final NutritionCalculationEngine calculationEngine;

    // -------------------------------------------------------------------------
    // ADMIN OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional
    public Ingredient createIngredient(UpsertIngredientRequest req) {
        if (ingredientRepository.findByVfcCode(req.getVfcCode()).isPresent()) {
            throw new BusinessRuleException(HttpStatus.CONFLICT, "Mã VFC đã tồn tại: " + req.getVfcCode());
        }
        Ingredient ing = new Ingredient();
        applyIngredientFields(ing, req);
        return ingredientRepository.save(ing);
    }

    @Transactional
    public Ingredient updateIngredientAndCascade(Long id, UpsertIngredientRequest req) {
        Ingredient ing = ingredientRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy nguyên liệu ID: " + id));
        applyIngredientFields(ing, req);
        Ingredient saved = ingredientRepository.save(ing);
        recalculateDishesContainingIngredient(id);
        return saved;
    }

    @Transactional(readOnly = true)
    public Page<Ingredient> searchIngredients(IngredientGroup group, GiLevel giLevel, String keyword, int page, int size) {
        String normalizedKw = VietnameseTextUtils.removeAccents(keyword);
        return ingredientRepository.searchIngredients(group, giLevel, normalizedKw, PageRequest.of(page, size));
    }

    @Transactional
    public void deleteIngredientSafely(Long id) {
        if (dishIngredientRepository.existsByIngredientId(id)) {
            throw new BusinessRuleException(HttpStatus.CONFLICT,
                    "Không thể xóa nguyên liệu này vì đang nằm trong công thức của một hoặc nhiều món ăn!");
        }
        ingredientRepository.deleteById(id);
    }

    @Transactional
    public YieldRetentionFactor upsertYieldFactor(UpsertYieldFactorRequest req) {
        YieldRetentionFactor yrf = YieldRetentionFactor.builder()
                .ingredientId(req.getIngredientId())
                .ingredientGroup(req.getIngredientGroup())
                .cookingMethod(req.getCookingMethod())
                .yieldFactor(req.getYieldFactor())
                .oilAbsorptionPct(req.getOilAbsorptionPct())
                .build();
        return yieldFactorRepository.save(yrf);
    }

    @Transactional(readOnly = true)
    public List<YieldRetentionFactor> getAllYieldFactors() {
        return yieldFactorRepository.findAll();
    }

    @Transactional
    public DishDetailResponse updateDishStatus(Long dishId, boolean isActive) {
        Dish dish = getDishOrThrow(dishId);
        dish.setIsActive(isActive);
        return DishDetailResponse.fromEntity(dishRepository.save(dish), false);
    }

    @Transactional
    public DishDetailResponse updateDishPopularity(Long dishId, int popularityScore) {
        Dish dish = getDishOrThrow(dishId);
        dish.setPopularityScore(popularityScore);
        return DishDetailResponse.fromEntity(dishRepository.save(dish), false);
    }

    @Transactional
    public DishDetailResponse updateServingRules(Long dishId, UpdateServingRulesRequest req) {
        Dish dish = getDishOrThrow(dishId);
        if (req.getMinServingScaledX2() > req.getMaxServingScaledX2()) {
            throw new BusinessRuleException(HttpStatus.BAD_REQUEST, "minServingScaledX2 không được lớn hơn maxServingScaledX2");
        }
        if (dish.getDishRole() == DishRole.COMPOSITE_DISH && req.getStepServingScaledX2() == 1) {
            throw new BusinessRuleException(HttpStatus.BAD_REQUEST,
                    "Món ăn trọn gói (COMPOSITE_DISH như Phở, Bún) bắt buộc stepServingScaledX2 = 2 để tránh CP-SAT gợi ý 0.5 tô!");
        }
        dish.setMinServingScaledX2(req.getMinServingScaledX2());
        dish.setMaxServingScaledX2(req.getMaxServingScaledX2());
        dish.setStepServingScaledX2(req.getStepServingScaledX2());
        dish.setHouseholdUnitLabel(req.getHouseholdUnitLabel());
        return DishDetailResponse.fromEntity(dishRepository.save(dish), false);
    }

    @Transactional
    public DishDetailResponse overrideMedicalTags(Long dishId, OverrideMedicalTagsRequest req) {
        Dish dish = getDishOrThrow(dishId);
        dish.setMedicalTags(new HashSet<>(req.getMedicalTags()));
        dish.setLockManualTags(req.getLockManualTags());
        return DishDetailResponse.fromEntity(dishRepository.save(dish), false);
    }

    @Transactional
    public BulkImportReportResponse bulkImportIngredients(List<UpsertIngredientRequest> items) {
        int inserted = 0;
        int updated = 0;
        List<String> errors = new ArrayList<>();

        for (int i = 0; i < items.size(); i++) {
            UpsertIngredientRequest req = items.get(i);
            try {
                Optional<Ingredient> existing = ingredientRepository.findByVfcCode(req.getVfcCode());
                if (existing.isPresent()) {
                    Ingredient ing = existing.get();
                    applyIngredientFields(ing, req);
                    ingredientRepository.save(ing);
                    updated++;
                } else {
                    Ingredient ing = new Ingredient();
                    applyIngredientFields(ing, req);
                    ingredientRepository.save(ing);
                    inserted++;
                }
            } catch (Exception e) {
                errors.add("Dòng " + (i + 1) + " (" + req.getVfcCode() + "): " + e.getMessage());
            }
        }
        return BulkImportReportResponse.builder()
                .totalProcessed(items.size())
                .insertedCount(inserted)
                .updatedCount(updated)
                .errors(errors)
                .build();
    }

    @Transactional(readOnly = true)
    public SimulationResultResponse simulateRecipeNutrition(SimulateRecipeRequest req) {
        Dish tempDish = new Dish();
        tempDish.setCookingMethod(req.getCookingMethod());

        List<DishIngredient> tempItems = new ArrayList<>();
        BigDecimal totalRawG = BigDecimal.ZERO;

        for (RecipeItemRequest itemReq : req.getRecipeItems()) {
            Ingredient ing = ingredientRepository.findById(itemReq.getIngredientId())
                    .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy nguyên liệu ID: " + itemReq.getIngredientId()));
            DishIngredient di = DishIngredient.builder()
                    .dish(tempDish)
                    .ingredient(ing)
                    .rawWeightG(itemReq.getRawWeightG())
                    .isMainIngredient(itemReq.isMainIngredient())
                    .build();
            tempItems.add(di);
            totalRawG = totalRawG.add(itemReq.getRawWeightG());
        }

        calculationEngine.computeNutritionAndMedicalTags(tempDish, tempItems);
        TrafficLightBadge badge = TrafficLightBadge.evaluate(tempDish.getEstimatedGi(), tempDish.getGlycemicLoad());

        List<String> recommendations = new ArrayList<>();
        if (tempDish.getMedicalTags().contains(MedicalTag.HIGH_GL)) {
            recommendations.add("Tải lượng đường huyết (GL = " + tempDish.getGlycemicLoad() + ") vượt ngưỡng 20. Hãy giảm 25% khối lượng tinh bột hoặc thêm rau xanh.");
        }
        if (tempDish.getMedicalTags().contains(MedicalTag.HIGH_SODIUM)) {
            recommendations.add("Lượng Natri (" + tempDish.getSodiumMg() + "mg) vượt ngưỡng 600mg/khẩu phần, rủi ro cho bệnh nhân kèm Tăng huyết áp.");
        }
        if (tempDish.getMedicalTags().contains(MedicalTag.HIGH_SATURATED_FAT)) {
            recommendations.add("Chất béo bão hòa cao. Khuyến nghị đổi sang phương pháp STEAMED (Hấp) hoặc BOILED (Luộc).");
        }
        if (recommendations.isEmpty()) {
            recommendations.add("Công thức đạt chuẩn an toàn y khoa cho bệnh nhân Đái tháo đường típ 2.");
        }

        return SimulationResultResponse.builder()
                .totalRawWeightG(totalRawG)
                .totalCookedWeightG(tempDish.getStandardServingCookedG())
                .caloriesKcal(tempDish.getCaloriesKcal())
                .totalCarbG(tempDish.getTotalCarbG())
                .fiberG(tempDish.getFiberG())
                .netCarbG(tempDish.getNetCarbG())
                .proteinG(tempDish.getProteinG())
                .fatG(tempDish.getFatG())
                .saturatedFatG(tempDish.getSaturatedFatG())
                .sodiumMg(tempDish.getSodiumMg())
                .potassiumMg(tempDish.getPotassiumMg())
                .purineMg(tempDish.getPurineMg())
                .estimatedGi(tempDish.getEstimatedGi())
                .giLevel(tempDish.getGiLevel())
                .glycemicLoad(tempDish.getGlycemicLoad())
                .trafficLightBadge(badge)
                .triggeredMedicalTags(tempDish.getMedicalTags())
                .medicalRecommendations(recommendations)
                .build();
    }

    @Transactional
    public DishDetailResponse createDish(CreateDishRequest req, Long createdByUserId) {
        Dish dish = new Dish();
        dish.setCreatedByUserId(createdByUserId);
        populateAndComputeDish(dish, req);
        return DishDetailResponse.fromEntity(dishRepository.save(dish), true);
    }

    @Transactional
    public DishDetailResponse updateDish(Long dishId, CreateDishRequest req) {
        Dish dish = getDishOrThrow(dishId);
        dish.getIngredients().clear();
        populateAndComputeDish(dish, req);
        return DishDetailResponse.fromEntity(dishRepository.save(dish), true);
    }

    @Transactional
    public CascadeRecalculationResponse recalculateDishesContainingIngredient(Long ingredientId) {
        Ingredient ing = ingredientRepository.findById(ingredientId)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy nguyên liệu ID: " + ingredientId));

        List<Long> dishIds = dishIngredientRepository.findDishIdsByIngredientId(ingredientId);
        List<Dish> affectedDishes = dishRepository.findAllById(dishIds);
        List<String> updatedCodes = new ArrayList<>();

        for (Dish dish : affectedDishes) {
            calculationEngine.computeNutritionAndMedicalTags(dish, dish.getIngredients());
            dishRepository.save(dish);
            updatedCodes.add(dish.getCode());
        }
        return CascadeRecalculationResponse.builder()
                .ingredientId(ing.getId())
                .ingredientName(ing.getNameVi())
                .affectedDishesCount(updatedCodes.size())
                .updatedDishCodes(updatedCodes)
                .build();
    }

    @Transactional(readOnly = true)
    public SolverCoverageDiagnosticResponse analyzeSolverCoverage(SolverCoverageDiagnosticRequest req) {
        BigDecimal maxGi = req.getMaxGiAllowed() != null ? req.getMaxGiAllowed() : new BigDecimal("69.9");
        Set<MedicalTag> excludedTags = (req.getExcludedMedicalTags() == null || req.getExcludedMedicalTags().isEmpty())
                ? Set.of(MedicalTag.HIGH_GI) : req.getExcludedMedicalTags();
        boolean hasExIds = req.getExcludedRecentDishIds() != null && !req.getExcludedRecentDishIds().isEmpty();
        Set<Long> safeExIds = hasExIds ? req.getExcludedRecentDishIds() : Set.of(-1L);

        List<Dish> eligible = dishRepository.findCandidatesForSolver(
                null, maxGi, EnumSet.allOf(MealSlot.class), hasExIds, safeExIds, excludedTags
        );

        Map<MealSlot, Map<DishRole, Integer>> matrix = new EnumMap<>(MealSlot.class);
        for (MealSlot slot : MealSlot.values()) {
            Map<DishRole, Integer> roleCounts = new EnumMap<>(DishRole.class);
            for (DishRole role : DishRole.values()) roleCounts.put(role, 0);
            matrix.put(slot, roleCounts);
        }

        for (Dish d : eligible) {
            for (MealSlot slot : d.getMealSlots()) {
                matrix.get(slot).merge(d.getDishRole(), 1, Integer::sum);
            }
        }

        List<String> warnings = new ArrayList<>();
        for (MealSlot mainSlot : List.of(MealSlot.LUNCH, MealSlot.DINNER)) {
            for (DishRole requiredRole : List.of(DishRole.MAIN_STARCH, DishRole.PROTEIN_DISH, DishRole.VEGGIE_DISH, DishRole.SOUP)) {
                int count = matrix.get(mainSlot).getOrDefault(requiredRole, 0);
                if (count < 2) {
                    warnings.add(String.format(
                            "NGUY CƠ INFEASIBLE tại [%s - %s]: Chỉ còn %d món hợp lệ (Cần tối thiểu >= 2 món).",
                            mainSlot, requiredRole, count));
                }
            }
        }

        return SolverCoverageDiagnosticResponse.builder()
                .isSolverReady(warnings.isEmpty())
                .totalEligibleDishes(eligible.size())
                .slotRoleMatrix(matrix)
                .bottleneckWarnings(warnings)
                .build();
    }

    // -------------------------------------------------------------------------
    // USER - PATIENT OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional(readOnly = true)
    public Page<DishDetailResponse> searchDishesForUser(
            Long userId, DishRole role, MealSlot slot, GiLevel giLevel, String keyword, int page, int size) {
        String normalizedKw = VietnameseTextUtils.removeAccents(keyword);
        return dishRepository.searchDishesForUser(userId, role, slot, giLevel, normalizedKw, PageRequest.of(page, size))
                .map(d -> DishDetailResponse.fromEntity(d, false));
    }

    @Transactional(readOnly = true)
    public DishDetailResponse getDishDetail(Long dishId) {
        return DishDetailResponse.fromEntity(getDishOrThrow(dishId), true);
    }

    @Transactional
    public void setUserDishPreference(Long userId, Long dishId, PreferenceType type) {
        Dish dish = getDishOrThrow(dishId);
        UserFoodPreference pref = preferenceRepository.findByUserIdAndDishId(userId, dishId)
                .orElse(UserFoodPreference.builder()
                        .userId(userId)
                        .dish(dish)
                        .preferenceType(type)
                        .build());
        pref.setPreferenceType(type);
        pref.setUpdatedAt(LocalDateTime.now());
        preferenceRepository.save(pref);
    }

    @Transactional(readOnly = true)
    public UserPreferenceResponse getUserPreferences(Long userId) {
        List<UserFoodPreference> prefs = preferenceRepository.findByUserId(userId);
        List<DishDetailResponse> favorites = prefs.stream()
                .filter(p -> p.getPreferenceType() == PreferenceType.FAVORITE)
                .map(p -> DishDetailResponse.fromEntity(p.getDish(), false))
                .toList();
        List<DishDetailResponse> dislikes = prefs.stream()
                .filter(p -> p.getPreferenceType() == PreferenceType.DISLIKE)
                .map(p -> DishDetailResponse.fromEntity(p.getDish(), false))
                .toList();
        return UserPreferenceResponse.builder()
                .userId(userId)
                .favoriteDishes(favorites)
                .dislikedDishes(dislikes)
                .build();
    }

    @Transactional(readOnly = true)
    public DynamicServingResponse calculateDynamicServing(Long dishId, BigDecimal multiplier) {
        if (multiplier == null || multiplier.compareTo(new BigDecimal("0.25")) < 0 || multiplier.compareTo(new BigDecimal("4.0")) > 0) {
            throw new BusinessRuleException(HttpStatus.BAD_REQUEST, "Hệ số khẩu phần (multiplier) phải nằm trong khoảng [0.25, 4.0]");
        }
        Dish d = getDishOrThrow(dishId);

        BigDecimal adjCookedG = d.getStandardServingCookedG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjCal = d.getCaloriesKcal().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjNetCarb = d.getNetCarbG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjFiber = d.getFiberG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjProtein = d.getProteinG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjFat = d.getFatG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjSodium = d.getSodiumMg().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);
        BigDecimal adjGl = d.getGlycemicLoad().multiply(multiplier).setScale(1, RoundingMode.HALF_UP);

        TrafficLightBadge badge = TrafficLightBadge.evaluate(d.getEstimatedGi(), adjGl);
        boolean isGlExceeded = adjGl.compareTo(new BigDecimal("20.0")) >= 0;
        String warningMsg = isGlExceeded
                ? String.format("CẢNH BÁO: Nếu ăn %.1f khẩu phần này, tải lượng đường huyết (GL) tăng lên %s (>= 20), dễ gây tăng đường huyết sau ăn!", multiplier, adjGl)
                : "Lượng đường huyết của khẩu phần này nằm trong ngưỡng an toàn.";

        List<RecipeIngredientBreakdownDto> adjIngredients = d.getIngredients().stream()
                .map(di -> RecipeIngredientBreakdownDto.builder()
                        .ingredientId(di.getIngredient().getId())
                        .ingredientNameVi(di.getIngredient().getNameVi())
                        .rawWeightG(di.getRawWeightG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP))
                        .appliedYieldFactor(di.getAppliedYieldFactor())
                        .cookedWeightG(di.getCookedWeightG().multiply(multiplier).setScale(1, RoundingMode.HALF_UP))
                        .isMainIngredient(Boolean.TRUE.equals(di.getIsMainIngredient()))
                        .build()).toList();

        return DynamicServingResponse.builder()
                .dishId(d.getId())
                .dishNameVi(d.getNameVi())
                .multiplier(multiplier)
                .adjustedHouseholdLabel(multiplier.stripTrailingZeros().toPlainString() + " x (" + d.getHouseholdUnitLabel() + ")")
                .adjustedCookedWeightG(adjCookedG)
                .caloriesKcal(adjCal)
                .netCarbG(adjNetCarb)
                .fiberG(adjFiber)
                .proteinG(adjProtein)
                .fatG(adjFat)
                .sodiumMg(adjSodium)
                .estimatedGi(d.getEstimatedGi())
                .adjustedGlycemicLoad(adjGl)
                .adjustedBadge(badge)
                .isGlExceededWarning(isGlExceeded)
                .medicalWarningMessage(warningMsg)
                .adjustedIngredients(adjIngredients)
                .build();
    }

    @Transactional(readOnly = true)
    public SafetyCheckResponse checkPersonalizedSafety(Long dishId, SafetyCheckRequest req) {
        Dish d = getDishOrThrow(dishId);
        Set<MedicalTag> conflicts = new HashSet<>(d.getMedicalTags());
        if (req.getPatientContraindications() != null) {
            conflicts.retainAll(req.getPatientContraindications());
        } else {
            conflicts.clear();
        }

        List<String> warnings = new ArrayList<>();
        List<String> tips = new ArrayList<>();

        BigDecimal maxGl = req.getMaxAllowedGlPerMeal() != null ? req.getMaxAllowedGlPerMeal() : new BigDecimal("20.0");
        if (d.getGlycemicLoad().compareTo(maxGl) > 0) {
            warnings.add("Tải lượng đường huyết của món (" + d.getGlycemicLoad() + ") vượt quá giới hạn mỗi bữa của bạn (" + maxGl + ").");
            tips.add("Hãy giảm khẩu phần ăn xuống 0.5 khẩu phần và ăn kèm rau lá xanh luộc trước.");
        }
        if (conflicts.contains(MedicalTag.HIGH_SODIUM)) {
            warnings.add("Hàm lượng Natri cao (" + d.getSodiumMg() + "mg), không phù hợp với bệnh Tăng huyết áp.");
            tips.add("Giảm 50% lượng muối/nước mắm khi chế biến và hạn chế chan nước kho.");
        }
        if (conflicts.contains(MedicalTag.HIGH_SATURATED_FAT)) {
            warnings.add("Giàu chất béo bão hòa (" + d.getSaturatedFatG() + "g), cần hạn chế với Rối loạn mỡ máu.");
            tips.add("Bỏ da/mỡ động vật và ưu tiên luộc hoặc hấp.");
        }

        boolean isSafe = conflicts.isEmpty() && warnings.isEmpty();
        return SafetyCheckResponse.builder()
                .dishId(d.getId())
                .dishNameVi(d.getNameVi())
                .isSafeForPatient(isSafe)
                .badge(TrafficLightBadge.evaluate(d.getEstimatedGi(), d.getGlycemicLoad()))
                .conflictingTags(conflicts)
                .detailedWarnings(warnings)
                .cookingAdjustmentTips(tips)
                .build();
    }

    @Transactional(readOnly = true)
    public List<DishDetailResponse> findAlternatives(Long dishId, MealSlot mealSlot) {
        Dish current = getDishOrThrow(dishId);
        BigDecimal minCarb = current.getNetCarbG().multiply(new BigDecimal("0.80")).subtract(new BigDecimal("5.0")).max(BigDecimal.ZERO);
        BigDecimal maxCarb = current.getNetCarbG().multiply(new BigDecimal("1.20")).add(new BigDecimal("5.0"));
        BigDecimal minCal = current.getCaloriesKcal().multiply(new BigDecimal("0.80"));
        BigDecimal maxCal = current.getCaloriesKcal().multiply(new BigDecimal("1.20"));

        return dishRepository.findSimilarAlternatives(
                        current.getId(), current.getDishRole(), mealSlot,
                        minCarb, maxCarb, minCal, maxCal, current.getGlycemicLoad())
                .stream()
                .limit(10)
                .map(d -> DishDetailResponse.fromEntity(d, false))
                .toList();
    }

    @Transactional(readOnly = true)
    public DishComparisonResponse compareTwoDishes(Long dish1Id, Long dish2Id) {
        Dish d1 = getDishOrThrow(dish1Id);
        Dish d2 = getDishOrThrow(dish2Id);

        Dish better = d1.getGlycemicLoad().compareTo(d2.getGlycemicLoad()) <= 0 ? d1 : d2;
        Dish worse = better == d1 ? d2 : d1;

        String summary = String.format(
                "Nên ưu tiên chọn [%s] vì có Tải lượng đường huyết thấp hơn (GL = %s so với %s của %s) và cung cấp %sg chất xơ.",
                better.getNameVi(), better.getGlycemicLoad(), worse.getGlycemicLoad(), worse.getNameVi(), better.getFiberG()
        );

        return DishComparisonResponse.builder()
                .dish1(DishDetailResponse.fromEntity(d1, false))
                .dish2(DishDetailResponse.fromEntity(d2, false))
                .netCarbDiffG(d1.getNetCarbG().subtract(d2.getNetCarbG()))
                .fiberDiffG(d1.getFiberG().subtract(d2.getFiberG()))
                .giDiff(d1.getEstimatedGi().subtract(d2.getEstimatedGi()))
                .glDiff(d1.getGlycemicLoad().subtract(d2.getGlycemicLoad()))
                .recommendedDishIdForDiabetic(better.getId())
                .comparisonSummaryVi(summary)
                .build();
    }

    // -------------------------------------------------------------------------
    // INTERNAL CP-SAT SOLVER OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional(readOnly = true)
    public List<DishSolverDto> getCandidateDishesForSolver(CandidateFilterRequest req) {
        Set<Long> mergedExcludedIds = new HashSet<>(req.getExcludedRecentDishIds() != null ? req.getExcludedRecentDishIds() : Set.of());
        Set<Long> mergedLikedIds = new HashSet<>(req.getLikedDishIds() != null ? req.getLikedDishIds() : Set.of());

        if (req.getUserId() != null) {
            for (UserFoodPreference pref : preferenceRepository.findByUserId(req.getUserId())) {
                if (pref.getPreferenceType() == PreferenceType.DISLIKE) {
                    mergedExcludedIds.add(pref.getDish().getId());
                } else if (pref.getPreferenceType() == PreferenceType.FAVORITE) {
                    mergedLikedIds.add(pref.getDish().getId());
                }
            }
        }

        boolean hasExcludedIds = !mergedExcludedIds.isEmpty();
        Set<Long> safeExcludedIds = hasExcludedIds ? mergedExcludedIds : Set.of(-1L);
        Set<MedicalTag> safeExcludedTags = (req.getExcludedMedicalTags() == null || req.getExcludedMedicalTags().isEmpty())
                ? Set.of(MedicalTag.HIGH_GI) : req.getExcludedMedicalTags();
        Set<MealSlot> slots = (req.getRequiredMealSlots() == null || req.getRequiredMealSlots().isEmpty())
                ? EnumSet.allOf(MealSlot.class) : req.getRequiredMealSlots();
        int limitPerRole = (req.getMaxCandidatesPerRole() == null || req.getMaxCandidatesPerRole() <= 0)
                ? 25 : req.getMaxCandidatesPerRole();

        List<Dish> rawCandidates = dishRepository.findCandidatesForSolver(
                req.getUserId(), req.getMaxGiAllowed(), slots, hasExcludedIds, safeExcludedIds, safeExcludedTags
        );

        Map<DishRole, List<Dish>> groupedByRole = rawCandidates.stream()
                .collect(Collectors.groupingBy(Dish::getDishRole));

        List<DishSolverDto> result = new ArrayList<>();
        for (Map.Entry<DishRole, List<Dish>> entry : groupedByRole.entrySet()) {
            entry.getValue().stream()
                    .limit(limitPerRole)
                    .map(d -> toSolverDto(d, mergedLikedIds.contains(d.getId())))
                    .forEach(result::add);
        }
        return result;
    }

    @Transactional(readOnly = true)
    public DishSolverDto getSingleSolverDto(Long dishId) {
        return toSolverDto(getDishOrThrow(dishId), false);
    }

    @Transactional(readOnly = true)
    public List<DishDetailResponse> getBatchDetails(List<Long> dishIds) {
        return dishRepository.findAllById(dishIds).stream()
                .map(d -> DishDetailResponse.fromEntity(d, false))
                .toList();
    }

    // -------------------------------------------------------------------------
    // HELPERS
    // -------------------------------------------------------------------------
    private Dish getDishOrThrow(Long dishId) {
        return dishRepository.findById(dishId)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy món ăn ID: " + dishId));
    }

    private void applyIngredientFields(Ingredient ing, UpsertIngredientRequest req) {
        ing.setVfcCode(req.getVfcCode());
        ing.setNameVi(req.getNameVi());
        ing.setIngredientGroup(req.getIngredientGroup());
        if (req.getEdiblePortionPct() != null) ing.setEdiblePortionPct(req.getEdiblePortionPct());
        ing.setCaloriesPer100g(req.getCaloriesPer100g());
        ing.setTotalCarbG(req.getTotalCarbG());
        ing.setFiberG(req.getFiberG());
        ing.setProteinG(req.getProteinG());
        ing.setFatG(req.getFatG());
        ing.setSaturatedFatG(req.getSaturatedFatG() != null ? req.getSaturatedFatG() : BigDecimal.ZERO);
        ing.setSodiumMg(req.getSodiumMg() != null ? req.getSodiumMg() : BigDecimal.ZERO);
        ing.setPotassiumMg(req.getPotassiumMg() != null ? req.getPotassiumMg() : BigDecimal.ZERO);
        ing.setPurineMg(req.getPurineMg() != null ? req.getPurineMg() : BigDecimal.ZERO);
        ing.setGiValue(req.getGiValue());
        ing.setAllergenTags(req.getAllergenTags() != null ? new HashSet<>(req.getAllergenTags()) : new HashSet<>());
    }

    private void populateAndComputeDish(Dish dish, CreateDishRequest req) {
        dish.setCode(req.getCode());
        dish.setNameVi(req.getNameVi());
        dish.setImageUrl(req.getImageUrl());
        dish.setDiabeticCookingTip(req.getDiabeticCookingTip());
        dish.setCookingMethod(req.getCookingMethod());
        dish.setDishRole(req.getDishRole());
        dish.setHouseholdUnitLabel(req.getHouseholdUnitLabel());
        dish.setMealSlots(new HashSet<>(req.getMealSlots()));

        if (req.getDishRole() == DishRole.COMPOSITE_DISH) {
            dish.setMinServingScaledX2(2);
            dish.setMaxServingScaledX2(2);
            dish.setStepServingScaledX2(2);
        } else if (req.getMinServingScaledX2() != null && req.getMaxServingScaledX2() != null) {
            dish.setMinServingScaledX2(req.getMinServingScaledX2());
            dish.setMaxServingScaledX2(req.getMaxServingScaledX2());
            dish.setStepServingScaledX2(req.getStepServingScaledX2() != null ? req.getStepServingScaledX2() : 1);
        } else {
            dish.setMinServingScaledX2(1);
            dish.setMaxServingScaledX2(3);
            dish.setStepServingScaledX2(1);
        }

        List<DishIngredient> dishIngredients = new ArrayList<>();
        for (RecipeItemRequest itemReq : req.getRecipeItems()) {
            Ingredient ing = ingredientRepository.findById(itemReq.getIngredientId())
                    .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy nguyên liệu ID: " + itemReq.getIngredientId()));
            DishIngredient di = DishIngredient.builder()
                    .dish(dish)
                    .ingredient(ing)
                    .rawWeightG(itemReq.getRawWeightG())
                    .isMainIngredient(itemReq.isMainIngredient())
                    .build();
            dishIngredients.add(di);
        }

        dish.getIngredients().addAll(dishIngredients);
        calculationEngine.computeNutritionAndMedicalTags(dish, dish.getIngredients());
    }

    private DishSolverDto toSolverDto(Dish d, boolean isUserFavorite) {
        int finalScore = d.getPopularityScore() + (isUserFavorite ? 150 : 0);
        return DishSolverDto.builder()
                .dishId(d.getId())
                .code(d.getCode())
                .nameVi(d.getNameVi())
                .role(d.getDishRole())
                .ingredientGroup(d.getPrimaryIngredientGroup())
                .validMealSlots(d.getMealSlots())
                .caloriesX10(d.getCaloriesScaledX10())
                .netCarbX10(d.getNetCarbScaledX10())
                .fiberX10(d.getFiberScaledX10())
                .proteinX10(d.getProteinScaledX10())
                .fatX10(d.getFatScaledX10())
                .glX10(d.getGlScaledX10())
                .minServingX2(d.getMinServingScaledX2())
                .maxServingX2(d.getMaxServingScaledX2())
                .stepServingX2(d.getStepServingScaledX2())
                .basePreferenceScore(finalScore)
                .build();
    }
}
