package com.example.mealoptimizerservice.service;

import com.example.mealoptimizerservice.client.FoodCatalogIntegrationClient;
import com.example.mealoptimizerservice.dto.*;
import com.example.mealoptimizerservice.dto.request.*;
import com.example.mealoptimizerservice.dto.response.*;
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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class MealOptimizerService {

    private final SolverWeightProfileRepository profileRepo;
    private final MealSlotTemplateRepository templateRepo;
    private final MealPlanRepository mealPlanRepo;
    private final CuratedFallbackPlanRepository fallbackRepo;
    private final SolverAuditLogRepository auditLogRepo;
    private final FoodCatalogIntegrationClient catalogClient;
    private final CpSatMealOptimizationEngine cpSatEngine;

    @Qualifier("cpSatSolverBulkheadExecutor")
    private final ThreadPoolTaskExecutor solverExecutor;

    // -------------------------------------------------------------------------
    // ADMIN OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional(readOnly = true)
    public List<SolverWeightProfile> getAllWeightProfiles() {
        return profileRepo.findAll();
    }

    @Transactional
    public SolverWeightProfile createWeightProfile(SolverWeightProfile req) {
        return profileRepo.save(req);
    }

    @Transactional
    public SolverWeightProfile updateWeightProfile(Long id, SolverWeightProfile req) {
        SolverWeightProfile existing = profileRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy cấu hình trọng số ID: " + id));
        existing.setNameVi(req.getNameVi());
        existing.setWeightCarbDeviation(req.getWeightCarbDeviation());
        existing.setWeightGlycemicLoad(req.getWeightGlycemicLoad());
        existing.setWeightCalorieDeviation(req.getWeightCalorieDeviation());
        existing.setWeightProteinFatDeviation(req.getWeightProteinFatDeviation());
        existing.setWeightFiberBonus(req.getWeightFiberBonus());
        existing.setWeightPreferenceBonus(req.getWeightPreferenceBonus());
        existing.setMaxTimeSeconds(req.getMaxTimeSeconds());
        existing.setNumSearchWorkers(req.getNumSearchWorkers());
        return profileRepo.save(existing);
    }

    @Transactional
    public SolverWeightProfile activateDefaultProfile(Long id) {
        List<SolverWeightProfile> all = profileRepo.findAll();
        SolverWeightProfile activated = null;
        for (SolverWeightProfile p : all) {
            p.setIsDefault(Objects.equals(p.getId(), id));
            if (p.getIsDefault()) activated = p;
        }
        profileRepo.saveAll(all);
        if (activated == null) {
            throw new ResourceNotFoundException("Không tìm thấy cấu hình trọng số ID: " + id);
        }
        return activated;
    }

    @Transactional(readOnly = true)
    public List<MealSlotTemplate> getMealTemplates(String templateCode) {
        return templateRepo.findByTemplateCodeOrderByIdAsc(templateCode);
    }

    @Transactional
    public MealSlotTemplate updateMealTemplate(Long id, MealSlotTemplate req) {
        MealSlotTemplate tpl = templateRepo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy mẫu bữa ăn ID: " + id));
        tpl.setCalorieRatioPct(req.getCalorieRatioPct());
        tpl.setMinNetCarbG(req.getMinNetCarbG());
        tpl.setMaxNetCarbG(req.getMaxNetCarbG());
        tpl.setMaxGl(req.getMaxGl());
        return templateRepo.save(tpl);
    }

    @Transactional(readOnly = true)
    public Page<SolverAuditLog> getAuditLogs(int page, int size) {
        return auditLogRepo.findAllByOrderByExecutedAtDesc(PageRequest.of(page, size));
    }

    @Transactional(readOnly = true)
    public SolverMetricsSummaryResponse getMetricsSummary() {
        List<SolverAuditLog> logs = auditLogRepo.findAll();
        long total = logs.size();
        long optimal = logs.stream().filter(l -> l.getSolverStatus() == SolverRunStatus.OPTIMAL).count();
        long feasible = logs.stream().filter(l -> l.getSolverStatus() == SolverRunStatus.FEASIBLE).count();
        long infeasible = logs.stream().filter(l -> l.getSolverStatus() == SolverRunStatus.INFEASIBLE).count();
        double avgMs = logs.stream().mapToLong(l -> l.getSolveTimeMs() != null ? l.getSolveTimeMs() : 0L).average().orElse(0.0);

        return SolverMetricsSummaryResponse.builder()
                .totalRuns(total)
                .optimalCount(optimal)
                .feasibleCount(feasible)
                .infeasibleCount(infeasible)
                .successRatePct(total > 0 ? ((optimal + feasible) * 100.0 / total) : 100.0)
                .avgSolveTimeMs(Math.round(avgMs * 10.0) / 10.0)
                .activeSolverThreads(solverExecutor.getActiveCount())
                .queuedSolverTasks(solverExecutor.getThreadPoolExecutor().getQueue().size())
                .build();
    }

    @Transactional
    public CuratedFallbackPlan createCuratedFallbackPlan(CuratedFallbackPlan plan) {
        return fallbackRepo.save(plan);
    }

    @Transactional(readOnly = true)
    public List<CuratedFallbackPlan> getAllCuratedFallbackPlans() {
        return fallbackRepo.findAllByOrderByTargetCalorieLevelAsc();
    }

    @Transactional
    public MealPlanResponse executeDryRunSandbox(GenerateDailyMealRequest req) {
        return runOptimizationPipeline(null, req, false, "DRY_RUN");
    }

    @Transactional
    public BenchmarkComparisonResponse benchmarkTwoProfiles(BenchmarkComparisonRequest req) {
        SolverWeightProfile pA = profileRepo.findById(req.getProfileIdA())
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy Profile A: " + req.getProfileIdA()));
        SolverWeightProfile pB = profileRepo.findById(req.getProfileIdB())
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy Profile B: " + req.getProfileIdB()));

        req.getSampleRequest().setEnableRandomPerturbation(false);
        req.getSampleRequest().setWeightProfileId(pA.getId());
        MealPlanResponse resA = runOptimizationPipeline(null, req.getSampleRequest(), false, "BENCHMARK_A");

        req.getSampleRequest().setWeightProfileId(pB.getId());
        MealPlanResponse resB = runOptimizationPipeline(null, req.getSampleRequest(), false, "BENCHMARK_B");

        String conclusion = String.format(
                "Profile [%s] cho Tổng GL = %s (Lệch Carb: %sg, Thời gian: %dms) | Profile [%s] cho Tổng GL = %s (Lệch Carb: %sg, Thời gian: %dms).",
                pA.getNameVi(), resA.getActualTotalGl(),
                resA.getActualNetCarbG().subtract(resA.getTargetNetCarbG()).abs(), resA.getSolveTimeMs(),
                pB.getNameVi(), resB.getActualTotalGl(),
                resB.getActualNetCarbG().subtract(resB.getTargetNetCarbG()).abs(), resB.getSolveTimeMs()
        );

        return BenchmarkComparisonResponse.builder()
                .profileNameA(pA.getNameVi())
                .resultA(resA)
                .profileNameB(pB.getNameVi())
                .resultB(resB)
                .comparisonConclusionVi(conclusion)
                .build();
    }

    @Transactional(readOnly = true)
    public InfeasibilityDiagnosisResponse explainInfeasibility(GenerateDailyMealRequest req) {
        List<MealSlotTemplate> slots = getActiveTemplateOrThrow(req.getTemplateCode());
        List<DishSolverDto> candidates = catalogClient.fetchCandidatesForSolver(
                req.getMaxGiAllowed(), req.getPatientContraindications(), Set.of());
        SolverWeightProfile wp = getActiveWeightProfile(req.getWeightProfileId());

        List<String> conflicts = new ArrayList<>();
        List<String> recommendations = new ArrayList<>();

        // Kiểm tra số lượng ứng viên từng nhóm
        for (MealSlotTemplate slotTpl : slots) {
            MealSlot slot = slotTpl.getMealSlot();
            if (Boolean.TRUE.equals(slotTpl.getAllowCompositeDish())) {
                long count = candidates.stream()
                        .filter(d -> d.getValidMealSlots().contains(slot) && d.getRole() == DishRole.COMPOSITE_DISH)
                        .count();
                if (count == 0) {
                    conflicts.add("Khung giờ [" + slot + "] yêu cầu món COMPOSITE_DISH nhưng kho ứng viên sau khi lọc = 0.");
                    recommendations.add("Bổ sung thêm món Phở/Bún/Cháo yến mạch GI thấp cho bữa sáng.");
                }
            }
        }

        // Chạy thử với chế độ chuẩn
        CpSatMealOptimizationEngine.SolverInputContext baseCtx = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(req.getTargetCaloriesKcal())
                .targetNetCarbG(req.getTargetNetCarbG())
                .targetProteinG(req.getTargetProteinG())
                .targetFatG(req.getTargetFatG())
                .activeSlots(slots)
                .candidates(candidates)
                .weightProfile(wp)
                .build();

        CpSatMealOptimizationEngine.SolverExecutionResult baseRes = cpSatEngine.solveOptimalMealPlan(baseCtx);
        if (baseRes.getStatus() != SolverRunStatus.INFEASIBLE) {
            return InfeasibilityDiagnosisResponse.builder()
                    .isFeasibleUnderStandardRules(true)
                    .detectedConflicts(List.of("Mô hình hoàn toàn khả thi (FEASIBLE/OPTIMAL), không có xung đột ràng buộc cứng."))
                    .actionableRecommendations(List.of("Có thể tiến hành tạo thực đơn bình thường."))
                    .build();
        }

        // Thử nới lỏng trần Carb/GL từng bữa
        baseCtx.setEnforcePerMealCarbAndGlCeiling(false);
        CpSatMealOptimizationEngine.SolverExecutionResult relaxCarbRes = cpSatEngine.solveOptimalMealPlan(baseCtx);
        if (relaxCarbRes.getStatus() != SolverRunStatus.INFEASIBLE) {
            conflicts.add("Xung đột tại Ràng buộc [Meal Carb & GL Ceiling]: Khoảng [minNetCarbG, maxNetCarbG] hoặc trần maxGl của từng bữa quá hẹp so với định lượng các món hiện có.");
            recommendations.add("Nới rộng khoảng minNetCarbG..maxNetCarbG trong MealSlotTemplate thêm +/- 10g.");
        }

        return InfeasibilityDiagnosisResponse.builder()
                .isFeasibleUnderStandardRules(false)
                .detectedConflicts(conflicts)
                .actionableRecommendations(recommendations)
                .build();
    }

    // -------------------------------------------------------------------------
    // USER - PATIENT OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional(readOnly = true)
    public Page<MealPlanResponse> getUserMealPlans(Long userId, int page, int size) {
        return mealPlanRepo.findByUserIdOrderByPlanDateDesc(userId, PageRequest.of(page, size))
                .map(mp -> MealPlanResponse.fromEntity(mp, null, null));
    }

    @Transactional(readOnly = true)
    public MealPlanResponse getMealPlanDetail(Long userId, Long planId) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        return MealPlanResponse.fromEntity(plan, null, evaluateMedicalWarnings(plan));
    }

    @Transactional
    public void deleteMealPlan(Long userId, Long planId) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        mealPlanRepo.delete(plan);
    }

    @Transactional
    public MealPlanResponse updateMealItemStatus(Long userId, Long planId, Long itemId, MealItemStatus status) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        MealPlanItem target = plan.getItems().stream()
                .filter(i -> Objects.equals(i.getId(), itemId))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy món ăn trong thực đơn ID: " + itemId));
        target.setStatus(status);
        plan.recalculateTotalsFromItems();
        return MealPlanResponse.fromEntity(mealPlanRepo.save(plan), null, evaluateMedicalWarnings(plan));
    }

    @Transactional
    public MealPlanResponse toggleMealItemLock(Long userId, Long planId, Long itemId, boolean isLocked) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        MealPlanItem target = plan.getItems().stream()
                .filter(i -> Objects.equals(i.getId(), itemId))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy món ăn trong thực đơn ID: " + itemId));
        target.setIsLocked(isLocked);
        return MealPlanResponse.fromEntity(mealPlanRepo.save(plan), null, null);
    }

    @Transactional
    public MealPlanResponse rateMealPlan(Long userId, Long planId, RateMealPlanRequest req) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        plan.setUserRating(req.getRating());
        plan.setUserFeedback(req.getFeedback());
        return MealPlanResponse.fromEntity(mealPlanRepo.save(plan), null, null);
    }

    @Transactional(readOnly = true)
    public ShoppingListResponse generateSmartShoppingList(Long userId, LocalDate fromDate, LocalDate toDate) {
        List<MealPlan> plans = mealPlanRepo.findByUserIdAndPlanDateBetweenOrderByPlanDateAsc(userId, fromDate, toDate);
        Map<Long, ShoppingListResponse.ShoppingItemDto> aggregated = new LinkedHashMap<>();
        int totalMeals = 0;

        for (MealPlan plan : plans) {
            for (MealPlanItem item : plan.getItems()) {
                if (item.getStatus() == MealItemStatus.SKIPPED) continue;
                totalMeals++;
                catalogClient.findDishById(item.getDishId()).ifPresent(dto -> {
                    if (dto.getRawIngredientsPerServing() != null) {
                        for (DishSolverDto.RawIngredientNeedDto rawNeed : dto.getRawIngredientsPerServing().values()) {
                            BigDecimal neededG = rawNeed.getRawWeightG()
                                    .multiply(item.getServingMultiplier())
                                    .setScale(1, RoundingMode.HALF_UP);
                            aggregated.compute(rawNeed.getIngredientId(), (k, existing) -> {
                                if (existing == null) {
                                    return ShoppingListResponse.ShoppingItemDto.builder()
                                            .ingredientId(rawNeed.getIngredientId())
                                            .ingredientNameVi(rawNeed.getIngredientNameVi())
                                            .group(rawNeed.getGroup())
                                            .totalRawWeightG(neededG)
                                            .build();
                                }
                                existing.setTotalRawWeightG(existing.getTotalRawWeightG().add(neededG));
                                return existing;
                            });
                        }
                    }
                });
            }
        }

        return ShoppingListResponse.builder()
                .fromDate(fromDate)
                .toDate(toDate)
                .totalMealsIncluded(totalMeals)
                .items(new ArrayList<>(aggregated.values()))
                .build();
    }

    @Transactional
    public MealPlanResponse manualReplaceMealItem(Long userId, Long planId, Long itemId, ManualReplaceItemRequest req) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        MealPlanItem item = plan.getItems().stream()
                .filter(i -> Objects.equals(i.getId(), itemId))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy mục thực đơn ID: " + itemId));

        DishSolverDto newDish = catalogClient.findDishById(req.getNewDishId())
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy món ăn thay thế ID: " + req.getNewDishId()));

        populateItemSnapshotFromSolverDto(item, newDish, req.getNewServingScaledX2());
        item.setStatus(MealItemStatus.MODIFIED);
        plan.recalculateTotalsFromItems();

        MealPlan saved = mealPlanRepo.save(plan);
        return MealPlanResponse.fromEntity(saved, null, evaluateMedicalWarnings(saved));
    }

    @Transactional(readOnly = true)
    public NutritionalAnalyticsResponse getNutritionalAnalytics(Long userId, int days) {
        LocalDate from = LocalDate.now().minusDays(days);
        List<MealPlan> plans = mealPlanRepo.findByUserIdAndPlanDateBetweenOrderByPlanDateAsc(userId, from, LocalDate.now().plusDays(1));
        if (plans.isEmpty()) {
            return NutritionalAnalyticsResponse.builder()
                    .analyzedDays(0).completedItemsCount(0)
                    .adherenceRatePct(BigDecimal.ZERO)
                    .avgDailyCaloriesKcal(BigDecimal.ZERO)
                    .avgDailyNetCarbG(BigDecimal.ZERO)
                    .avgDailyFiberG(BigDecimal.ZERO)
                    .avgDailyGl(BigDecimal.ZERO)
                    .build();
        }

        int totalItems = 0;
        int completedItems = 0;
        BigDecimal sumCal = BigDecimal.ZERO;
        BigDecimal sumCarb = BigDecimal.ZERO;
        BigDecimal sumFiber = BigDecimal.ZERO;
        BigDecimal sumGl = BigDecimal.ZERO;

        for (MealPlan p : plans) {
            sumCal = sumCal.add(p.getActualCaloriesKcal());
            sumCarb = sumCarb.add(p.getActualNetCarbG());
            sumFiber = sumFiber.add(p.getActualFiberG());
            sumGl = sumGl.add(p.getActualTotalGl());
            for (MealPlanItem item : p.getItems()) {
                totalItems++;
                if (item.getStatus() == MealItemStatus.COMPLETED) completedItems++;
            }
        }

        BigDecimal countBd = BigDecimal.valueOf(plans.size());
        BigDecimal adherence = totalItems > 0
                ? BigDecimal.valueOf(completedItems * 100.0 / totalItems).setScale(1, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;

        return NutritionalAnalyticsResponse.builder()
                .analyzedDays(plans.size())
                .completedItemsCount(completedItems)
                .adherenceRatePct(adherence)
                .avgDailyCaloriesKcal(sumCal.divide(countBd, 1, RoundingMode.HALF_UP))
                .avgDailyNetCarbG(sumCarb.divide(countBd, 1, RoundingMode.HALF_UP))
                .avgDailyFiberG(sumFiber.divide(countBd, 1, RoundingMode.HALF_UP))
                .avgDailyGl(sumGl.divide(countBd, 1, RoundingMode.HALF_UP))
                .build();
    }

    // --- [CORE CP-SAT] 1. SINH THỰC ĐƠN 1 NGÀY TỐI ƯU ---
    @Transactional
    public MealPlanResponse generateOptimalDailyMealPlan(Long userId, GenerateDailyMealRequest req) {
        mealPlanRepo.findByUserIdAndPlanDate(userId, req.getPlanDate())
                .ifPresent(mealPlanRepo::delete);
        return runOptimizationPipeline(userId, req, true, "DAILY_GEN");
    }

    // --- [CORE CP-SAT] 2. ĐỔI 1 MÓN LẺ TỨC THÌ (PARTIAL RE-OPTIMIZATION) ---
    @Transactional
    public MealPlanResponse swapSingleDishInPlan(Long userId, Long planId, SwapSingleDishRequest req) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);
        MealPlanItem droppedItem = plan.getItems().stream()
                .filter(i -> Objects.equals(i.getId(), req.getDroppedMealPlanItemId()))
                .findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy món cần đổi ID: " + req.getDroppedMealPlanItemId()));

        // Khóa toàn bộ các món khác trong thực đơn, chỉ cấm món bị bỏ
        Map<MealSlot, Set<Long>> lockedMap = new EnumMap<>(MealSlot.class);
        Map<MealSlot, Set<Long>> forbiddenMap = new EnumMap<>(MealSlot.class);

        for (MealPlanItem item : plan.getItems()) {
            if (!Objects.equals(item.getId(), droppedItem.getId())) {
                lockedMap.computeIfAbsent(item.getMealSlot(), k -> new HashSet<>()).add(item.getDishId());
            } else {
                Set<Long> forbidden = forbiddenMap.computeIfAbsent(item.getMealSlot(), k -> new HashSet<>());
                forbidden.add(item.getDishId());
                if (req.getAdditionalExcludedDishIds() != null) {
                    forbidden.addAll(req.getAdditionalExcludedDishIds());
                }
            }
        }

        List<MealSlotTemplate> slots = getActiveTemplateOrThrow("STANDARD_4_MEALS");
        List<DishSolverDto> candidates = catalogClient.fetchCandidatesForSolver(
                new BigDecimal("69.9"), Set.of(), Set.of());
        SolverWeightProfile wp = getActiveWeightProfile(null);

        CpSatMealOptimizationEngine.SolverInputContext ctx = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(plan.getTargetCaloriesKcal())
                .targetNetCarbG(plan.getTargetNetCarbG())
                .targetProteinG(plan.getTargetProteinG())
                .targetFatG(plan.getTargetFatG())
                .activeSlots(slots)
                .candidates(candidates)
                .weightProfile(wp)
                .enableRandomPerturbation(true)
                .lockedDishIdsBySlot(lockedMap)
                .forbiddenDishIdsBySlot(forbiddenMap)
                .build();

        CpSatMealOptimizationEngine.SolverExecutionResult result = executeInsideBulkhead(ctx);
        if (result.getStatus() == SolverRunStatus.INFEASIBLE) {
            throw new OptimizerBusinessException(HttpStatus.UNPROCESSABLE_ENTITY,
                    "Không tìm được món thay thế khả thi thỏa mãn trần đường huyết của bữa " + droppedItem.getMealSlot());
        }

        // Cập nhật lại danh sách món và khẩu phần mới sau khi tái cân bằng
        Map<Long, Boolean> previousLocks = new HashMap<>();
        plan.getItems().forEach(i -> previousLocks.put(i.getDishId(), i.getIsLocked()));
        plan.getItems().clear();

        for (CpSatMealOptimizationEngine.SelectedDishSolution sel : result.getSelectedDishes()) {
            MealPlanItem newItem = new MealPlanItem();
            newItem.setMealPlan(plan);
            newItem.setMealSlot(sel.getMealSlot());
            newItem.setIsLocked(previousLocks.getOrDefault(sel.getDish().getDishId(), false));
            populateItemSnapshotFromSolverDto(newItem, sel.getDish(), sel.getServingScaledX2());
            plan.getItems().add(newItem);
        }

        plan.setSolverStatus(result.getStatus());
        plan.setSolveTimeMs(result.getBreakdown().getSolveTimeMs());
        plan.recalculateTotalsFromItems();

        recordAuditLog(userId, "SWAP_DISH", result);
        MealPlan saved = mealPlanRepo.save(plan);
        return MealPlanResponse.fromEntity(saved, result.getBreakdown(), evaluateMedicalWarnings(saved));
    }

    // --- [CORE CP-SAT] 3. TÁI CÂN BẰNG CÁC BỮA CÒN LẠI TRONG NGÀY ---
    @Transactional
    public MealPlanResponse rebalanceRemainingMeals(Long userId, Long planId, RebalanceRemainingMealsRequest req) {
        MealPlan plan = getMealPlanOrThrow(userId, planId);

        BigDecimal remainingCal = plan.getTargetCaloriesKcal().subtract(req.getConsumedCaloriesKcal()).max(new BigDecimal("350.0"));
        BigDecimal remainingCarb = plan.getTargetNetCarbG().subtract(req.getConsumedNetCarbG()).max(new BigDecimal("35.0"));
        BigDecimal remainingProt = plan.getTargetProteinG().subtract(req.getConsumedProteinG()).max(new BigDecimal("25.0"));
        BigDecimal remainingFat = plan.getTargetFatG().subtract(req.getConsumedFatG()).max(new BigDecimal("10.0"));

        List<MealSlotTemplate> remainingSlots = getActiveTemplateOrThrow("STANDARD_4_MEALS").stream()
                .filter(s -> !req.getAlreadyEatenSlots().contains(s.getMealSlot()))
                .toList();

        if (remainingSlots.isEmpty()) {
            throw new OptimizerBusinessException(HttpStatus.BAD_REQUEST, "Tất cả các bữa trong ngày đều đã được ăn!");
        }

        List<DishSolverDto> candidates = catalogClient.fetchCandidatesForSolver(new BigDecimal("69.9"), Set.of(), Set.of());
        SolverWeightProfile wp = getActiveWeightProfile(null);

        CpSatMealOptimizationEngine.SolverInputContext ctx = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(remainingCal)
                .targetNetCarbG(remainingCarb)
                .targetProteinG(remainingProt)
                .targetFatG(remainingFat)
                .activeSlots(remainingSlots)
                .candidates(candidates)
                .weightProfile(wp)
                .enableRandomPerturbation(false)
                .build();

        CpSatMealOptimizationEngine.SolverExecutionResult result = executeInsideBulkhead(ctx);
        if (result.getStatus() == SolverRunStatus.INFEASIBLE) {
            throw new OptimizerBusinessException(HttpStatus.UNPROCESSABLE_ENTITY,
                    "Không thể tái cân bằng với ngân sách dinh dưỡng còn lại.");
        }

        // Giữ nguyên các bữa đã ăn, thay thế các bữa chưa ăn bằng nghiệm CP-SAT mới
        plan.getItems().removeIf(i -> !req.getAlreadyEatenSlots().contains(i.getMealSlot()));
        for (CpSatMealOptimizationEngine.SelectedDishSolution sel : result.getSelectedDishes()) {
            MealPlanItem newItem = new MealPlanItem();
            newItem.setMealPlan(plan);
            newItem.setMealSlot(sel.getMealSlot());
            populateItemSnapshotFromSolverDto(newItem, sel.getDish(), sel.getServingScaledX2());
            plan.getItems().add(newItem);
        }

        plan.recalculateTotalsFromItems();
        recordAuditLog(userId, "REBALANCE_REMAINING", result);
        MealPlan saved = mealPlanRepo.save(plan);
        return MealPlanResponse.fromEntity(saved, result.getBreakdown(), evaluateMedicalWarnings(saved));
    }

    // --- [CORE CP-SAT] 4. SINH THỰC ĐƠN 7 NGÀY LIÊN TIẾP CHỐNG LẶP MÓN (SLIDING WINDOW) ---
    @Transactional
    public List<MealPlanResponse> generateWeeklyMealPlans(Long userId, GenerateWeeklyMealRequest req) {
        List<MealPlanResponse> weeklyResults = new ArrayList<>();
        Deque<Set<Long>> slidingWindow2Days = new ArrayDeque<>();

        for (int dayOffset = 0; dayOffset < 7; dayOffset++) {
            LocalDate currentDate = req.getStartDate().plusDays(dayOffset);
            mealPlanRepo.findByUserIdAndPlanDate(userId, currentDate).ifPresent(mealPlanRepo::delete);

            GenerateDailyMealRequest dayReq = GenerateDailyMealRequest.builder()
                    .planDate(currentDate)
                    .targetCaloriesKcal(req.getDailyTargetTemplate().getTargetCaloriesKcal())
                    .targetNetCarbG(req.getDailyTargetTemplate().getTargetNetCarbG())
                    .targetProteinG(req.getDailyTargetTemplate().getTargetProteinG())
                    .targetFatG(req.getDailyTargetTemplate().getTargetFatG())
                    .maxGiAllowed(req.getDailyTargetTemplate().getMaxGiAllowed())
                    .patientContraindications(req.getDailyTargetTemplate().getPatientContraindications())
                    .templateCode(req.getDailyTargetTemplate().getTemplateCode())
                    .weightProfileId(req.getDailyTargetTemplate().getWeightProfileId())
                    .enableRandomPerturbation(true)
                    .build();

            Set<Long> excludedFromWindow = new HashSet<>();
            slidingWindow2Days.forEach(excludedFromWindow::addAll);

            MealPlanResponse dayPlan = runOptimizationPipelineWithExtraExclusions(
                    userId, dayReq, excludedFromWindow, true, "WEEKLY_DAY_" + (dayOffset + 1));
            weeklyResults.add(dayPlan);

            // Đưa các món मặn/canh/bữa sáng của ngày hôm nay vào cửa sổ cấm 2 ngày kế tiếp
            Set<Long> todaysMainDishes = new HashSet<>();
            dayPlan.getMealsBySlot().values().forEach(list -> list.forEach(item -> {
                if (item.getDishRole() == DishRole.PROTEIN_DISH
                        || item.getDishRole() == DishRole.COMPOSITE_DISH
                        || item.getDishRole() == DishRole.SOUP) {
                    todaysMainDishes.add(item.getDishId());
                }
            }));
            slidingWindow2Days.addLast(todaysMainDishes);
            if (slidingWindow2Days.size() > 1) {
                slidingWindow2Days.removeFirst();
            }
        }
        return weeklyResults;
    }

    // -------------------------------------------------------------------------
    // INTERNAL OPERATIONS
    // -------------------------------------------------------------------------
    @Transactional(readOnly = true)
    public Set<Long> getRecentEatenDishIds(Long userId, int days) {
        return mealPlanRepo.findRecentDishIdsByUserId(userId, LocalDate.now().minusDays(days));
    }

    // -------------------------------------------------------------------------
    // PRIVATE HELPERS & BULKHEAD EXECUTION
    // -------------------------------------------------------------------------
    private MealPlanResponse runOptimizationPipeline(
            Long userId, GenerateDailyMealRequest req, boolean persistToDb, String operationType) {
        Set<Long> recentDishes = (userId != null)
                ? mealPlanRepo.findRecentDishIdsByUserId(userId, req.getPlanDate().minusDays(2))
                : Collections.emptySet();
        return runOptimizationPipelineWithExtraExclusions(userId, req, recentDishes, persistToDb, operationType);
    }

    private MealPlanResponse runOptimizationPipelineWithExtraExclusions(
            Long userId, GenerateDailyMealRequest req, Set<Long> excludedDishIds, boolean persistToDb, String operationType) {

        List<MealSlotTemplate> slots = getActiveTemplateOrThrow(req.getTemplateCode());
        List<DishSolverDto> candidates = catalogClient.fetchCandidatesForSolver(
                req.getMaxGiAllowed(), req.getPatientContraindications(), excludedDishIds);
        SolverWeightProfile wp = getActiveWeightProfile(req.getWeightProfileId());

        CpSatMealOptimizationEngine.SolverInputContext ctx = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(req.getTargetCaloriesKcal())
                .targetNetCarbG(req.getTargetNetCarbG())
                .targetProteinG(req.getTargetProteinG())
                .targetFatG(req.getTargetFatG())
                .activeSlots(slots)
                .candidates(candidates)
                .weightProfile(wp)
                .enableRandomPerturbation(req.isEnableRandomPerturbation())
                .build();

        CpSatMealOptimizationEngine.SolverExecutionResult result = executeInsideBulkhead(ctx);
        recordAuditLog(userId, operationType, result);

        MealPlan plan = MealPlan.builder()
                .userId(userId != null ? userId : 0L)
                .planDate(req.getPlanDate())
                .targetCaloriesKcal(req.getTargetCaloriesKcal())
                .targetNetCarbG(req.getTargetNetCarbG())
                .targetProteinG(req.getTargetProteinG())
                .targetFatG(req.getTargetFatG())
                .solverStatus(result.getStatus())
                .solveTimeMs(result.getBreakdown().getSolveTimeMs())
                .items(new ArrayList<>())
                .build();

        for (CpSatMealOptimizationEngine.SelectedDishSolution sel : result.getSelectedDishes()) {
            MealPlanItem item = new MealPlanItem();
            item.setMealPlan(plan);
            item.setMealSlot(sel.getMealSlot());
            populateItemSnapshotFromSolverDto(item, sel.getDish(), sel.getServingScaledX2());
            plan.getItems().add(item);
        }

        plan.recalculateTotalsFromItems();
        if (persistToDb && result.getStatus() != SolverRunStatus.INFEASIBLE) {
            plan = mealPlanRepo.save(plan);
        }

        return MealPlanResponse.fromEntity(plan, result.getBreakdown(), evaluateMedicalWarnings(plan));
    }

    private CpSatMealOptimizationEngine.SolverExecutionResult executeInsideBulkhead(
            CpSatMealOptimizationEngine.SolverInputContext ctx) {
        try {
            return CompletableFuture.supplyAsync(() -> cpSatEngine.solveOptimalMealPlan(ctx), solverExecutor)
                    .get(5, TimeUnit.SECONDS);
        } catch (Exception e) {
            log.error("Lỗi khi thực thi CP-SAT trong Bulkhead ThreadPool", e);
            throw new OptimizerBusinessException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Bộ giải tối ưu thực đơn đang quá tải, vui lòng thử lại sau giây lát.");
        }
    }

    private void populateItemSnapshotFromSolverDto(MealPlanItem item, DishSolverDto dish, int servingScaledX2) {
        BigDecimal multiplier = BigDecimal.valueOf(servingScaledX2)
                .divide(new BigDecimal("2.0"), 2, RoundingMode.HALF_UP);

        item.setDishId(dish.getDishId());
        item.setDishCode(dish.getCode());
        item.setDishNameVi(dish.getNameVi());
        item.setDishRole(dish.getRole());
        item.setIngredientGroup(dish.getIngredientGroup());
        item.setServingScaledX2(servingScaledX2);
        item.setServingMultiplier(multiplier);
        item.setHouseholdUnitDisplay(multiplier.stripTrailingZeros().toPlainString() + " x (" + dish.getHouseholdUnitLabel() + ")");

        // Chuyển từ (Nutr_X10 * servingScaledX2) / 20 về giá trị thực Snapshot
        item.setSnapshotCaloriesKcal(unscaleX20(dish.getCaloriesX10() * servingScaledX2));
        item.setSnapshotNetCarbG(unscaleX20(dish.getNetCarbX10() * servingScaledX2));
        item.setSnapshotFiberG(unscaleX20(dish.getFiberX10() * servingScaledX2));
        item.setSnapshotProteinG(unscaleX20(dish.getProteinX10() * servingScaledX2));
        item.setSnapshotFatG(unscaleX20(dish.getFatX10() * servingScaledX2));
        item.setSnapshotGl(unscaleX20(dish.getGlX10() * servingScaledX2));
    }

    private static BigDecimal unscaleX20(long valX20) {
        return BigDecimal.valueOf(valX20).divide(new BigDecimal("20.0"), 2, RoundingMode.HALF_UP);
    }

    private List<String> evaluateMedicalWarnings(MealPlan plan) {
        List<String> warnings = new ArrayList<>();
        Map<MealSlot, BigDecimal> glBySlot = new EnumMap<>(MealSlot.class);
        for (MealPlanItem item : plan.getItems()) {
            if (item.getStatus() != MealItemStatus.SKIPPED) {
                glBySlot.merge(item.getMealSlot(), item.getSnapshotGl(), BigDecimal::add);
            }
        }
        for (Map.Entry<MealSlot, BigDecimal> entry : glBySlot.entrySet()) {
            if (entry.getValue().compareTo(new BigDecimal("20.0")) > 0) {
                warnings.add("CẢNH BÁO ĐƯỜNG HUYẾT: Bữa [" + entry.getKey() + "] có tổng GL = "
                        + entry.getValue() + " (vượt ngưỡng an toàn 20.0).");
            }
        }
        if (warnings.isEmpty()) {
            warnings.add("Tất cả các bữa ăn đều đạt ngưỡng an toàn Tải lượng Đường huyết (GL <= 20/bữa).");
        }
        return warnings;
    }

    private void recordAuditLog(Long userId, String opType, CpSatMealOptimizationEngine.SolverExecutionResult res) {
        MathematicalBreakdownDto b = res.getBreakdown();
        BigDecimal calDev = (b.getCalOverKcal() != null && b.getCalUnderKcal() != null)
                ? b.getCalOverKcal().add(b.getCalUnderKcal()) : BigDecimal.ZERO;
        BigDecimal carbDev = (b.getCarbOverG() != null && b.getCarbUnderG() != null)
                ? b.getCarbOverG().add(b.getCarbUnderG()) : BigDecimal.ZERO;

        auditLogRepo.save(SolverAuditLog.builder()
                .userId(userId)
                .operationType(opType)
                .solverStatus(res.getStatus())
                .candidateCount(b.getTotalCandidatesEvaluated())
                .solveTimeMs(b.getSolveTimeMs())
                .objectiveValue(b.getObjectiveValue())
                .calDeviationKcal(calDev)
                .carbDeviationG(carbDev)
                .build());
    }

    private MealPlan getMealPlanOrThrow(Long userId, Long planId) {
        MealPlan plan = mealPlanRepo.findById(planId)
                .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy thực đơn ID: " + planId));
        if (userId != null && !Objects.equals(plan.getUserId(), userId)) {
            throw new OptimizerBusinessException(HttpStatus.FORBIDDEN, "Bạn không có quyền truy cập thực đơn này!");
        }
        return plan;
    }

    private List<MealSlotTemplate> getActiveTemplateOrThrow(String code) {
        String safeCode = (code == null || code.isBlank()) ? "STANDARD_4_MEALS" : code;
        List<MealSlotTemplate> list = templateRepo.findByTemplateCodeOrderByIdAsc(safeCode);
        if (list.isEmpty()) {
            throw new ResourceNotFoundException("Không tìm thấy mẫu cấu trúc bữa ăn: " + safeCode);
        }
        return list;
    }

    private SolverWeightProfile getActiveWeightProfile(Long profileId) {
        if (profileId != null) {
            return profileRepo.findById(profileId)
                    .orElseThrow(() -> new ResourceNotFoundException("Không tìm thấy cấu hình trọng số ID: " + profileId));
        }
        return profileRepo.findFirstByIsDefaultTrue()
                .orElseGet(() -> SolverWeightProfile.builder().code("DEFAULT").nameVi("Mặc định").build());
    }
}
