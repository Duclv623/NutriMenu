package com.example.mealoptimizerservice.service;

import com.example.mealoptimizerservice.client.FoodCatalogIntegrationClient;
import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.dto.request.CheckedMealChangeRequest;
import com.example.mealoptimizerservice.dto.response.MealPlanResponse;
import com.example.mealoptimizerservice.entity.*;
import com.example.mealoptimizerservice.entity.enums.*;
import com.example.mealoptimizerservice.exception.OptimizerBusinessException;
import com.example.mealoptimizerservice.repository.*;
import com.example.mealoptimizerservice.solver.CpSatMealOptimizationEngine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

@Service
public class CheckedMealChangeService {
    private final MealPlanRepository plans;
    private final MealSlotTemplateRepository templates;
    private final SolverWeightProfileRepository weights;
    private final FoodCatalogIntegrationClient catalog;
    private final CpSatMealOptimizationEngine engine;
    private final ThreadPoolTaskExecutor executor;

    public CheckedMealChangeService(MealPlanRepository plans, MealSlotTemplateRepository templates,
            SolverWeightProfileRepository weights, FoodCatalogIntegrationClient catalog,
            CpSatMealOptimizationEngine engine, @Qualifier("cpSatSolverBulkheadExecutor") ThreadPoolTaskExecutor executor) {
        this.plans=plans; this.templates=templates; this.weights=weights; this.catalog=catalog; this.engine=engine; this.executor=executor;
    }

    private OptimizerBusinessException error(HttpStatus code, String text) {
        return new OptimizerBusinessException(code, text);
    }

    private MealPlan owned(Long user, Long id, boolean write) {
        return (write ? plans.findOwnedForUpdate(id, user) : plans.findById(id).filter(p -> p.getUserId().equals(user)))
                .orElseThrow(() -> error(HttpStatus.NOT_FOUND, "Không tìm thấy thực đơn thuộc tài khoản."));
    }

    @Transactional(readOnly=true)
    public MealPlanResponse preview(Long user, Long id, CheckedMealChangeRequest request) {
        return validate(owned(user,id,false), request).response();
    }

    @Transactional
    public MealPlanResponse apply(Long user, Long id, CheckedMealChangeRequest request) {
        MealPlan plan = owned(user,id,true);
        Validated result = validate(plan,request);
        if (request.getPreviewSignature()==null || !MessageDigest.isEqual(
                result.signature().getBytes(StandardCharsets.UTF_8), request.getPreviewSignature().getBytes(StandardCharsets.UTF_8)))
            throw error(HttpStatus.CONFLICT, "Phương án đã thay đổi. Hãy xem trước lại trước khi xác nhận.");
        MealPlanItem target = plan.getItems().stream().filter(i -> i.getId().equals(request.getItemId())).findFirst().orElseThrow();
        writeItem(target, result.dish(), request.getNewServingScaledX2());
        target.setStatus(MealItemStatus.MODIFIED);
        plan.setSolverStatus(SolverRunStatus.FEASIBLE);
        plan.setUpdatedAt(LocalDateTime.now());
        plan.recalculateTotalsFromItems();
        MealPlan saved = plans.saveAndFlush(plan);
        MealPlanResponse response = MealPlanResponse.fromEntity(saved,null,List.of("Thay đổi đã được kiểm tra bằng CP-SAT với các món và khẩu phần còn lại được giữ nguyên."));
        response.setValidationPassed(true);
        return response;
    }

    private record Validated(MealPlanResponse response, DishSolverDto dish, String signature) {}

    private Validated validate(MealPlan plan, CheckedMealChangeRequest request) {
        if (!Boolean.TRUE.equals(plan.getChangePolicyRecorded()))
            throw error(HttpStatus.CONFLICT,"Thực đơn cũ chưa lưu đủ quy tắc kiểm tra. Hãy tạo thực đơn mới trước khi đổi món.");
        if (!Objects.equals(plan.getVersion(), request.getExpectedVersion()))
            throw error(HttpStatus.CONFLICT,"Thực đơn đã thay đổi. Hãy tải lại và xem trước lại.");
        MealPlanItem target = plan.getItems().stream().filter(i -> i.getId().equals(request.getItemId())).findFirst()
                .orElseThrow(() -> error(HttpStatus.NOT_FOUND,"Không tìm thấy món cần đổi."));
        if (Boolean.TRUE.equals(target.getIsLocked())) throw error(HttpStatus.CONFLICT,"Hãy bỏ giữ món trước khi thay đổi.");
        if (target.getStatus()==MealItemStatus.COMPLETED) throw error(HttpStatus.CONFLICT,"Hãy bỏ ghi nhận đã ăn trước khi thay đổi món này.");
        if (plan.getItems().stream().anyMatch(i -> i.getStatus()==MealItemStatus.SKIPPED))
            throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Thực đơn có bữa đã bỏ; cần tái cân bằng trước khi đổi món.");
        if (target.getDishId().equals(request.getNewDishId()) && target.getServingScaledX2().equals(request.getNewServingScaledX2()))
            throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Hãy chọn món hoặc khẩu phần khác.");
        Set<MealSlot> slots = plan.getItems().stream().map(MealPlanItem::getMealSlot).collect(Collectors.toSet());
        List<MealSlotTemplate> active = templates.findByTemplateCodeOrderByIdAsc(plan.getTemplateCode()).stream()
                .filter(t -> slots.contains(t.getMealSlot())).toList();
        if (!active.stream().map(MealSlotTemplate::getMealSlot).collect(Collectors.toSet()).equals(slots))
            throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Thiếu cấu trúc bữa để kiểm tra thực đơn.");
        List<DishSolverDto> eligible = catalog.fetchCandidatesForSolver(plan.getUserId(), plan.getMaxGiAllowed(),
                request.getContraindications(), request.getExcludedDishIds(), slots);
        Map<Long,DishSolverDto> byId = eligible.stream().collect(Collectors.toMap(DishSolverDto::getDishId, d -> d, (a,b)->a));
        DishSolverDto replacement = byId.get(request.getNewDishId());
        if (replacement==null || replacement.getRole()!=target.getDishRole())
            throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Món thay thế không thuộc nhóm món hoặc bộ lọc hợp lệ.");
        Map<MealSlot,Map<Long,Integer>> pins = new EnumMap<>(MealSlot.class);
        List<MealPlanItem> previewItems = new ArrayList<>();
        Set<Long> desiredIds = new HashSet<>();
        StringBuilder signature = new StringBuilder(plan.getId()+":"+plan.getVersion()+":"+new TreeSet<>(request.getExcludedDishIds())+":"+new TreeSet<>(request.getContraindications()));
        for (MealPlanItem item : plan.getItems()) {
            boolean changed = item.getId().equals(target.getId());
            Long dishId = changed ? request.getNewDishId() : item.getDishId();
            int portions = changed ? request.getNewServingScaledX2() : item.getServingScaledX2();
            DishSolverDto dish = byId.get(dishId);
            if (dish==null || !dish.getValidMealSlots().contains(item.getMealSlot()) || portions<dish.getMinServingX2()
                    || portions>dish.getMaxServingX2() || dish.getStepServingX2()<1 || portions%dish.getStepServingX2()!=0)
                throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Có món hoặc khẩu phần không đáp ứng quy tắc danh mục hiện tại.");
            if (!desiredIds.add(dishId)) throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Món thay thế bị lặp trong ngày.");
            pins.computeIfAbsent(item.getMealSlot(), k->new HashMap<>()).put(dishId,portions);
            MealPlanItem preview = new MealPlanItem();
            preview.setId(item.getId()); preview.setMealSlot(item.getMealSlot());
            preview.setIsLocked(item.getIsLocked()); preview.setStatus(item.getStatus());
            writeItem(preview,dish,portions);
            if (!changed && !sameNutrition(item,preview))
                throw error(HttpStatus.CONFLICT,"Dữ liệu món đã thay đổi trong danh mục. Hãy cập nhật thực đơn trước khi đổi.");
            previewItems.add(preview);
            signature.append('|').append(item.getId()).append(':').append(item.getMealSlot()).append(':').append(dishId).append(':').append(portions)
                    .append(':').append(preview.getSnapshotCaloriesKcal()).append(':').append(preview.getSnapshotNetCarbG())
                    .append(':').append(preview.getSnapshotProteinG()).append(':').append(preview.getSnapshotFatG())
                    .append(':').append(preview.getSnapshotFiberG()).append(':').append(preview.getSnapshotGl())
                    .append(':').append(preview.getSnapshotSodiumMg()).append(':').append(preview.getSnapshotCholesterolMg());
            if (dish.getRawIngredientsPerServing()==null || dish.getRawIngredientsPerServing().isEmpty())
                throw error(HttpStatus.UNPROCESSABLE_ENTITY,"Thiếu nguyên liệu để kiểm tra món.");
            new TreeMap<>(dish.getRawIngredientsPerServing()).forEach((key,value) -> signature.append(':').append(key).append('=').append(value.getRawWeightG()));
        }
        Map<MealSlot,Set<Long>> forbidden = new EnumMap<>(MealSlot.class);
        for (MealSlot slot : slots) {
            Set<Long> ids = new HashSet<>(desiredIds);
            ids.removeAll(pins.get(slot).keySet());
            forbidden.put(slot,ids);
        }
        CpSatMealOptimizationEngine.SolverInputContext input = CpSatMealOptimizationEngine.SolverInputContext.builder()
                .targetCaloriesKcal(plan.getTargetCaloriesKcal()).targetNetCarbG(plan.getTargetNetCarbG())
                .targetProteinG(plan.getTargetProteinG()).targetFatG(plan.getTargetFatG())
                .maxDailyGl(plan.getMaxDailyGl()).maxDailySodiumMg(plan.getMaxDailySodiumMg())
                .maxDailyCholesterolMg(plan.getMaxDailyCholesterolMg()).minDailyFiberG(plan.getMinDailyFiberG())
                .activeSlots(active).candidates(eligible.stream().filter(d -> desiredIds.contains(d.getDishId())).toList())
                .weightProfile(weights.findFirstByIsDefaultTrue().orElseThrow(() -> error(HttpStatus.SERVICE_UNAVAILABLE,"Thiếu cấu hình solver.")))
                .fixedServingsBySlot(pins).forbiddenDishIdsBySlot(forbidden).enableRandomPerturbation(false).build();
        CpSatMealOptimizationEngine.SolverExecutionResult solved;
        try {
            solved = CompletableFuture.supplyAsync(() -> engine.solveOptimalMealPlan(input),executor).get(5, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw error(HttpStatus.SERVICE_UNAVAILABLE,"Kiểm tra thay đổi đã bị ngắt; chưa lưu.");
        } catch (Exception exception) {
            throw error(HttpStatus.SERVICE_UNAVAILABLE,"Chưa kiểm tra được phương án; thực đơn được giữ nguyên.");
        }
        if (solved.getStatus()!=SolverRunStatus.OPTIMAL && solved.getStatus()!=SolverRunStatus.FEASIBLE)
            throw error(solved.getStatus()==SolverRunStatus.INFEASIBLE ? HttpStatus.UNPROCESSABLE_ENTITY : HttpStatus.SERVICE_UNAVAILABLE,
                    "Phương án chưa đáp ứng các ràng buộc của bộ giải; thực đơn được giữ nguyên.");
        MealPlan previewPlan = MealPlan.builder().id(plan.getId()).userId(plan.getUserId()).version(plan.getVersion())
                .planDate(plan.getPlanDate()).targetCaloriesKcal(plan.getTargetCaloriesKcal()).targetNetCarbG(plan.getTargetNetCarbG())
                .targetProteinG(plan.getTargetProteinG()).targetFatG(plan.getTargetFatG()).solverStatus(SolverRunStatus.FEASIBLE)
                .items(previewItems).build();
        previewPlan.recalculateTotalsFromItems();
        String digest;
        try { digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(signature.toString().getBytes(StandardCharsets.UTF_8))); }
        catch (Exception exception) { throw new IllegalStateException(exception); }
        MealPlanResponse response = MealPlanResponse.fromEntity(previewPlan,solved.getBreakdown(),List.of("Xem trước đã được kiểm tra; chưa lưu thay đổi."));
        response.setChangeSignature(digest); response.setValidationPassed(true);
        return new Validated(response,replacement,digest);
    }

    private boolean sameNutrition(MealPlanItem a, MealPlanItem b) {
        return a.getSnapshotCaloriesKcal().compareTo(b.getSnapshotCaloriesKcal())==0
            && a.getSnapshotNetCarbG().compareTo(b.getSnapshotNetCarbG())==0
            && a.getSnapshotProteinG().compareTo(b.getSnapshotProteinG())==0
            && a.getSnapshotFatG().compareTo(b.getSnapshotFatG())==0
            && a.getSnapshotFiberG().compareTo(b.getSnapshotFiberG())==0
            && a.getSnapshotGl().compareTo(b.getSnapshotGl())==0
            && sameNumber(a.getSnapshotSodiumMg(),b.getSnapshotSodiumMg())
            && sameNumber(a.getSnapshotCholesterolMg(),b.getSnapshotCholesterolMg());
    }

    private boolean sameNumber(BigDecimal a, BigDecimal b) { return a!=null && b!=null && a.compareTo(b)==0; }

    private static BigDecimal amount(long scaled, int portions) { return BigDecimal.valueOf(scaled).multiply(BigDecimal.valueOf(portions)).divide(new BigDecimal("20.0")); }

    static void writeItem(MealPlanItem item, DishSolverDto dish, int portions) {
        item.setDishId(dish.getDishId()); item.setCatalogDish(true); item.setDishCode(dish.getCode()); item.setDishNameVi(dish.getNameVi());
        item.setDishRole(dish.getRole()); item.setIngredientGroup(dish.getIngredientGroup()); item.setServingScaledX2(portions);
        item.setServingMultiplier(BigDecimal.valueOf(portions).divide(new BigDecimal("2.0")));
        item.setHouseholdUnitDisplay(item.getServingMultiplier()+" x ("+dish.getHouseholdUnitLabel()+")");
        item.setSnapshotCaloriesKcal(amount(dish.getCaloriesX10(),portions)); item.setSnapshotNetCarbG(amount(dish.getNetCarbX10(),portions));
        item.setSnapshotProteinG(amount(dish.getProteinX10(),portions)); item.setSnapshotFatG(amount(dish.getFatX10(),portions));
        item.setSnapshotFiberG(amount(dish.getFiberX10(),portions)); item.setSnapshotGl(amount(dish.getGlX10(),portions));
        item.setSnapshotSodiumMg(amount(dish.getSodiumX10(),portions)); item.setSnapshotCholesterolMg(amount(dish.getCholesterolX10(),portions));
    }
}
