package com.example.mealoptimizerservice.solver;

import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.dto.MathematicalBreakdownDto;
import com.example.mealoptimizerservice.entity.MealSlotTemplate;
import com.example.mealoptimizerservice.entity.SolverWeightProfile;
import com.example.mealoptimizerservice.entity.enums.*;
import com.google.ortools.sat.*;
import lombok.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;

/**
 * LÕI THUẬT TOÁN QUY HOẠCH NGUYÊN GOOGLE OR-TOOLS CP-SAT
 * Đồng nhất hệ số nhân x20 (Scaled x20):
 *   - Dinh dưỡng món ăn: Scaled x10
 *   - Biến khẩu phần s[i,m]: Scaled x2 (1 = 0.5 khẩu phần, 2 = 1.0 khẩu phần, 3 = 1.5 khẩu phần)
 *   => Tích số (Nutr_X10 * s[i,m]) có đơn vị Scaled x20.
 */
@Slf4j
@Component
public class CpSatMealOptimizationEngine {

    @Data
    @Builder
    public static class SolverInputContext {
        private BigDecimal targetCaloriesKcal;
        private BigDecimal targetNetCarbG;
        private BigDecimal targetProteinG;
        private BigDecimal targetFatG;
        private List<MealSlotTemplate> activeSlots;
        private List<DishSolverDto> candidates;
        private SolverWeightProfile weightProfile;
        private boolean enableRandomPerturbation;

        // Phục vụ Đổi 1 món lẻ (Partial Re-optimization) & Khóa món (Pin)
        @Builder.Default
        private Map<MealSlot, Set<Long>> lockedDishIdsBySlot = Collections.emptyMap();
        @Builder.Default
        private Map<MealSlot, Set<Long>> forbiddenDishIdsBySlot = Collections.emptyMap();

        // Chế độ nới lỏng phục vụ chẩn đoán IIS
        @Builder.Default
        private boolean enforceAntiDuplicateProteinInMeal = true;
        @Builder.Default
        private boolean enforcePerMealCarbAndGlCeiling = true;
    }

    @Data
    @Builder
    public static class SelectedDishSolution {
        private MealSlot mealSlot;
        private DishSolverDto dish;
        private int servingScaledX2;
    }

    @Data
    @Builder
    public static class SolverExecutionResult {
        private SolverRunStatus status;
        private List<SelectedDishSolution> selectedDishes;
        private MathematicalBreakdownDto breakdown;
    }

    public SolverExecutionResult solveOptimalMealPlan(SolverInputContext ctx) {
        long startTime = System.currentTimeMillis();
        CpModel model = new CpModel();

        List<DishSolverDto> candidates = ctx.getCandidates();
        List<MealSlotTemplate> slots = ctx.getActiveSlots();

        // Map lưu biến quyết định: x[m][i] thuộc {0,1} và s[m][i] thuộc {0, min..max}
        Map<MealSlot, Map<Long, BoolVar>> xVars = new EnumMap<>(MealSlot.class);
        Map<MealSlot, Map<Long, IntVar>> sVars = new EnumMap<>(MealSlot.class);
        int totalDecisionVars = 0;

        // 1. KHỞI TẠO BIẾN QUYẾT ĐỊNH & RÀNG BUỘC KÊNH (CHANNELING CONSTRAINTS)
        for (MealSlotTemplate slotTpl : slots) {
            MealSlot slot = slotTpl.getMealSlot();
            xVars.put(slot, new HashMap<>());
            sVars.put(slot, new HashMap<>());

            for (DishSolverDto dish : candidates) {
                if (!dish.getValidMealSlots().contains(slot)) continue;

                String suffix = slot.name() + "_" + dish.getDishId();
                BoolVar x = model.newBoolVar("x_" + suffix);
                IntVar s = model.newIntVar(0, dish.getMaxServingX2(), "s_" + suffix);
                totalDecisionVars += 2;

                // Channeling: x = 0 => s = 0 ; x = 1 => minServingX2 <= s <= maxServingX2
                model.addEquality(s, 0).onlyEnforceIf(x.not());
                model.addGreaterOrEqual(s, dish.getMinServingX2()).onlyEnforceIf(x);
                model.addLessOrEqual(s, dish.getMaxServingX2()).onlyEnforceIf(x);

                // Nếu stepServingX2 == 2 (chỉ ăn khẩu phần chẵn 1.0, 2.0): cấm s = 1 hoặc s = 3
                if (dish.getStepServingX2() == 2) {
                    for (int odd = 1; odd <= dish.getMaxServingX2(); odd += 2) {
                        model.addDifferent(s, odd);
                    }
                }

                // Khóa món (Pin / Partial Re-optimization)
                if (ctx.getLockedDishIdsBySlot().getOrDefault(slot, Set.of()).contains(dish.getDishId())) {
                    model.addEquality(x, 1);
                }
                // Cấm món vừa bị người dùng bấm "Đổi món"
                if (ctx.getForbiddenDishIdsBySlot().getOrDefault(slot, Set.of()).contains(dish.getDishId())) {
                    model.addEquality(x, 0);
                }

                xVars.get(slot).put(dish.getDishId(), x);
                sVars.get(slot).put(dish.getDishId(), s);
            }
        }

        // 2. RÀNG BUỘC CỨNG: CẤU TRÚC MÂM CƠM VIỆT NAM & TRẦN ĐƯỜNG HUYẾT TỪNG BỮA
        for (MealSlotTemplate slotTpl : slots) {
            MealSlot slot = slotTpl.getMealSlot();
            Map<Long, BoolVar> slotX = xVars.get(slot);
            Map<Long, IntVar> slotS = sVars.get(slot);

            if (Boolean.TRUE.equals(slotTpl.getAllowCompositeDish())) {
                // Bữa sáng: Chọn đúng 1 món COMPOSITE_DISH (Phở, Bún, Cháo, Miến)
                List<Literal> compVars = filterVarsByRole(candidates, slotX, DishRole.COMPOSITE_DISH);
                if (!compVars.isEmpty()) {
                    model.addEquality(LinearExpr.sum(compVars.toArray(new Literal[0])), 1);
                }
            } else {
                // Bữa Trưa / Tối / Bữa Phụ: Ghép mâm theo đúng số lượng DishRole yêu cầu
                enforceExactRoleCount(model, candidates, slotX, DishRole.MAIN_STARCH, slotTpl.getReqMainStarch());
                enforceExactRoleCount(model, candidates, slotX, DishRole.PROTEIN_DISH, slotTpl.getReqProteinDish());
                enforceExactRoleCount(model, candidates, slotX, DishRole.VEGGIE_DISH, slotTpl.getReqVeggieDish());
                enforceExactRoleCount(model, candidates, slotX, DishRole.SOUP, slotTpl.getReqSoup());
                enforceExactRoleCount(model, candidates, slotX, DishRole.SNACK, slotTpl.getReqSnack());
            }

            // Kiểm soát Net Carb & GL từng bữa (Scaled x20)
            if (ctx.isEnforcePerMealCarbAndGlCeiling()) {
                LinearExprBuilder mealCarbX20 = LinearExpr.newBuilder();
                LinearExprBuilder mealGlX20 = LinearExpr.newBuilder();

                for (DishSolverDto dish : candidates) {
                    IntVar s = slotS.get(dish.getDishId());
                    if (s != null) {
                        mealCarbX20.addTerm(s, dish.getNetCarbX10());
                        mealGlX20.addTerm(s, dish.getGlX10());
                    }
                }

                long minCarbX20 = scaleToX20(slotTpl.getMinNetCarbG());
                long maxCarbX20 = scaleToX20(slotTpl.getMaxNetCarbG());
                long maxGlX20 = scaleToX20(slotTpl.getMaxGl());

                model.addLinearConstraint(mealCarbX20, minCarbX20, maxCarbX20);
                model.addLessOrEqual(mealGlX20, maxGlX20);
            }

            // Chống trùng lặp nhóm nguyên liệu đạm trong cùng 1 bữa (VD: Gà + Gà)
            if (ctx.isEnforceAntiDuplicateProteinInMeal()) {
                for (IngredientGroup proteinGroup : List.of(
                        IngredientGroup.PORK, IngredientGroup.BEEF, IngredientGroup.POULTRY,
                        IngredientGroup.FISH_SEAFOOD, IngredientGroup.SOY_TOFU)) {
                    List<Literal> groupVars = new ArrayList<>();
                    for (DishSolverDto dish : candidates) {
                        if (dish.getIngredientGroup() == proteinGroup && slotX.containsKey(dish.getDishId())) {
                            groupVars.add(slotX.get(dish.getDishId()));
                        }
                    }
                    if (groupVars.size() > 1) {
                        model.addLessOrEqual(LinearExpr.sum(groupVars.toArray(new Literal[0])), 1);
                    }
                }
            }
        }

        // 3. RÀNG BUỘC CỨNG: MỖI MÓN ĂN CHỈ XUẤT HIỆN TỐI ĐA 1 LẦN TRONG NGÀY
        for (DishSolverDto dish : candidates) {
            List<Literal> dishAcrossMeals = new ArrayList<>();
            for (MealSlotTemplate slotTpl : slots) {
                BoolVar x = xVars.get(slotTpl.getMealSlot()).get(dish.getDishId());
                if (x != null) dishAcrossMeals.add(x);
            }
            if (dishAcrossMeals.size() > 1) {
                model.addLessOrEqual(LinearExpr.sum(dishAcrossMeals.toArray(new Literal[0])), 1);
            }
        }

        // 4. BIẾN BÙ (SLACK VARIABLES) CHO TỔNG DINH DƯỠNG CẢ NGÀY (TRÁNH LỖI INFEASIBLE)
        LinearExprBuilder totalCalX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalCarbX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalProtX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalFatX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalFiberX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalGlX20 = LinearExpr.newBuilder();
        LinearExprBuilder totalPrefScore = LinearExpr.newBuilder();

        for (MealSlotTemplate slotTpl : slots) {
            MealSlot slot = slotTpl.getMealSlot();
            for (DishSolverDto dish : candidates) {
                IntVar s = sVars.get(slot).get(dish.getDishId());
                BoolVar x = xVars.get(slot).get(dish.getDishId());
                if (s == null || x == null) continue;

                totalCalX20.addTerm(s, dish.getCaloriesX10());
                totalCarbX20.addTerm(s, dish.getNetCarbX10());
                totalProtX20.addTerm(s, dish.getProteinX10());
                totalFatX20.addTerm(s, dish.getFatX10());
                totalFiberX20.addTerm(s, dish.getFiberX10());
                totalGlX20.addTerm(s, dish.getGlX10());

                int perturbation = ctx.isEnableRandomPerturbation()
                        ? ThreadLocalRandom.current().nextInt(-18, 19) : 0;
                totalPrefScore.addTerm(x, Math.max(10, dish.getBasePreferenceScore() + perturbation));
            }
        }

        long targetCalX20 = scaleToX20(ctx.getTargetCaloriesKcal());
        long targetCarbX20 = scaleToX20(ctx.getTargetNetCarbG());
        long targetProtX20 = scaleToX20(ctx.getTargetProteinG());
        long targetFatX20 = scaleToX20(ctx.getTargetFatG());

        IntVar calOver = model.newIntVar(0, 100_000, "cal_over");
        IntVar calUnder = model.newIntVar(0, 100_000, "cal_under");
        model.addEquality(LinearExpr.newBuilder().add(totalCalX20).add(calUnder).addTerm(calOver, -1), targetCalX20);

        IntVar carbOver = model.newIntVar(0, 20_000, "carb_over");
        IntVar carbUnder = model.newIntVar(0, 20_000, "carb_under");
        model.addEquality(LinearExpr.newBuilder().add(totalCarbX20).add(carbUnder).addTerm(carbOver, -1), targetCarbX20);

        IntVar protOver = model.newIntVar(0, 20_000, "prot_over");
        IntVar protUnder = model.newIntVar(0, 20_000, "prot_under");
        model.addEquality(LinearExpr.newBuilder().add(totalProtX20).add(protUnder).addTerm(protOver, -1), targetProtX20);

        IntVar fatOver = model.newIntVar(0, 20_000, "fat_over");
        IntVar fatUnder = model.newIntVar(0, 20_000, "fat_under");
        model.addEquality(LinearExpr.newBuilder().add(totalFatX20).add(fatUnder).addTerm(fatOver, -1), targetFatX20);

        // 5. THIẾT LẬP HÀM MỤC TIÊU ĐA TRỌNG SỐ (MINIMIZE Z)
        SolverWeightProfile wp = ctx.getWeightProfile();
        LinearExprBuilder objective = LinearExpr.newBuilder();

        // Phạt lệch Carb (Phạt nặng gấp 1.5 lần nếu thừa Carb so với thiếu Carb)
        objective.addTerm(carbOver, wp.getWeightCarbDeviation() * 3 / 2);
        objective.addTerm(carbUnder, wp.getWeightCarbDeviation());

        // Phạt tổng tải lượng đường huyết GL
        objective.addTerm(totalGlX20.build(), wp.getWeightGlycemicLoad());

        // Phạt lệch Calo, Đạm, Béo
        objective.addTerm(calOver, wp.getWeightCalorieDeviation());
        objective.addTerm(calUnder, wp.getWeightCalorieDeviation());
        objective.addTerm(protOver, wp.getWeightProteinFatDeviation());
        objective.addTerm(protUnder, wp.getWeightProteinFatDeviation());
        objective.addTerm(fatOver, wp.getWeightProteinFatDeviation());
        objective.addTerm(fatUnder, wp.getWeightProteinFatDeviation());

        // Thưởng Chất xơ & Điểm yêu thích (Mang dấu âm trong hàm Minimize)
        objective.addTerm(totalFiberX20.build(), -wp.getWeightFiberBonus());
        objective.addTerm(totalPrefScore.build(), -wp.getWeightPreferenceBonus());

        model.minimize(objective);

        // 6. KÍCH HOẠT CP-SAT SOLVER
        CpSolver solver = new CpSolver();
        solver.getParameters().setMaxTimeInSeconds(wp.getMaxTimeSeconds());
        solver.getParameters().setNumSearchWorkers(wp.getNumSearchWorkers());

        CpSolverStatus status = solver.solve(model);
        long elapsedMs = System.currentTimeMillis() - startTime;

        if (status == CpSolverStatus.OPTIMAL || status == CpSolverStatus.FEASIBLE) {
            List<SelectedDishSolution> selected = new ArrayList<>();
            for (MealSlotTemplate slotTpl : slots) {
                MealSlot slot = slotTpl.getMealSlot();
                for (DishSolverDto dish : candidates) {
                    BoolVar x = xVars.get(slot).get(dish.getDishId());
                    IntVar s = sVars.get(slot).get(dish.getDishId());
                    if (x != null && solver.booleanValue(x)) {
                        selected.add(SelectedDishSolution.builder()
                                .mealSlot(slot)
                                .dish(dish)
                                .servingScaledX2((int) solver.value(s))
                                .build());
                    }
                }
            }

            SolverRunStatus mappedStatus = (status == CpSolverStatus.OPTIMAL)
                    ? SolverRunStatus.OPTIMAL : SolverRunStatus.FEASIBLE;

            MathematicalBreakdownDto breakdown = MathematicalBreakdownDto.builder()
                    .solverStatus(mappedStatus)
                    .solveTimeMs(elapsedMs)
                    .objectiveValue(solver.objectiveValue())
                    .totalCandidatesEvaluated(candidates.size())
                    .totalDecisionVariables(totalDecisionVars)
                    .calOverKcal(unscaleFromX20(solver.value(calOver)))
                    .calUnderKcal(unscaleFromX20(solver.value(calUnder)))
                    .carbOverG(unscaleFromX20(solver.value(carbOver)))
                    .carbUnderG(unscaleFromX20(solver.value(carbUnder)))
                    .proteinOverG(unscaleFromX20(solver.value(protOver)))
                    .proteinUnderG(unscaleFromX20(solver.value(protUnder)))
                    .fatOverG(unscaleFromX20(solver.value(fatOver)))
                    .fatUnderG(unscaleFromX20(solver.value(fatUnder)))
                    .build();

            return SolverExecutionResult.builder()
                    .status(mappedStatus)
                    .selectedDishes(selected)
                    .breakdown(breakdown)
                    .build();
        }

        return SolverExecutionResult.builder()
                .status(SolverRunStatus.INFEASIBLE)
                .selectedDishes(Collections.emptyList())
                .breakdown(MathematicalBreakdownDto.builder()
                        .solverStatus(SolverRunStatus.INFEASIBLE)
                        .solveTimeMs(elapsedMs)
                        .totalCandidatesEvaluated(candidates.size())
                        .totalDecisionVariables(totalDecisionVars)
                        .build())
                .build();
    }

    private List<Literal> filterVarsByRole(List<DishSolverDto> candidates, Map<Long, BoolVar> slotX, DishRole role) {
        List<Literal> list = new ArrayList<>();
        for (DishSolverDto d : candidates) {
            if (d.getRole() == role && slotX.containsKey(d.getDishId())) {
                list.add(slotX.get(d.getDishId()));
            }
        }
        return list;
    }

    private void enforceExactRoleCount(
            CpModel model, List<DishSolverDto> candidates, Map<Long, BoolVar> slotX, DishRole role, int requiredCount) {
        List<Literal> roleVars = filterVarsByRole(candidates, slotX, role);
        if (!roleVars.isEmpty()) {
            model.addEquality(LinearExpr.sum(roleVars.toArray(new Literal[0])), requiredCount);
        } else if (requiredCount > 0) {
            // Không có ứng viên nào cho Role bắt buộc -> Ép mô hình báo INFEASIBLE rõ ràng
            BoolVar impossible = model.newBoolVar("missing_role_" + role);
            model.addEquality(impossible, 1);
            model.addEquality(impossible, 0);
        }
    }

    private static long scaleToX20(BigDecimal val) {
        if (val == null) return 0L;
        return val.multiply(new BigDecimal("20.0")).setScale(0, RoundingMode.HALF_UP).longValue();
    }

    private static BigDecimal unscaleFromX20(long scaledX20) {
        return BigDecimal.valueOf(scaledX20).divide(new BigDecimal("20.0"), 2, RoundingMode.HALF_UP);
    }
}
