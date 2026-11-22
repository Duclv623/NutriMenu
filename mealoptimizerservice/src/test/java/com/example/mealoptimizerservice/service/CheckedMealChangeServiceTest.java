package com.example.mealoptimizerservice.service;

import com.example.mealoptimizerservice.client.FoodCatalogIntegrationClient;
import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.dto.request.CheckedMealChangeRequest;
import com.example.mealoptimizerservice.entity.*;
import com.example.mealoptimizerservice.entity.enums.*;
import com.example.mealoptimizerservice.exception.OptimizerBusinessException;
import com.example.mealoptimizerservice.repository.*;
import com.example.mealoptimizerservice.solver.CpSatMealOptimizationEngine;
import com.google.ortools.Loader;
import org.junit.jupiter.api.*;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Real native CP-SAT; repository and catalog are controlled doubles, not a live DB test. */
class CheckedMealChangeServiceTest {
    MealPlanRepository plans;
    FoodCatalogIntegrationClient catalog;
    CheckedMealChangeService service;
    ThreadPoolTaskExecutor executor;
    MealPlan plan;
    DishSolverDto original, replacement;
    CheckedMealChangeRequest request;

    @BeforeAll static void nativeLibraries() { Loader.loadNativeLibraries(); }
    @BeforeEach void setup() {
        plans=mock(MealPlanRepository.class);
        catalog=mock(FoodCatalogIntegrationClient.class);
        var templates=mock(MealSlotTemplateRepository.class);
        var weights=mock(SolverWeightProfileRepository.class);
        executor=new ThreadPoolTaskExecutor(); executor.setCorePoolSize(1); executor.initialize();
        service=new CheckedMealChangeService(plans,templates,weights,catalog,new CpSatMealOptimizationEngine(),executor);
        original=dish(1L,400); replacement=dish(2L,450);
        MealPlanItem item=new MealPlanItem(); item.setId(11L); item.setMealSlot(MealSlot.BREAKFAST);
        item.setIsLocked(false); item.setStatus(MealItemStatus.PLANNED);
        CheckedMealChangeService.writeItem(item,original,2);
        plan=MealPlan.builder().id(7L).userId(99L).version(0L).changePolicyRecorded(true)
            .planDate(LocalDate.of(2026,11,21)).targetCaloriesKcal(new BigDecimal("400"))
            .targetNetCarbG(new BigDecimal("45")).targetProteinG(new BigDecimal("20"))
            .targetFatG(new BigDecimal("10")).solverStatus(SolverRunStatus.FEASIBLE)
            .items(new ArrayList<>(List.of(item))).build();
        item.setMealPlan(plan); plan.recalculateTotalsFromItems();
        when(plans.findById(7L)).thenReturn(Optional.of(plan));
        when(plans.findOwnedForUpdate(7L,99L)).thenReturn(Optional.of(plan));
        when(plans.saveAndFlush(any())).thenAnswer(call -> { MealPlan p=call.getArgument(0); p.setVersion(p.getVersion()+1); return p; });
        when(templates.findByTemplateCodeOrderByIdAsc("STANDARD_4_MEALS")).thenReturn(List.of(
            MealSlotTemplate.builder().mealSlot(MealSlot.BREAKFAST).allowCompositeDish(true)
                .calorieRatioPct(new BigDecimal("100")).minNetCarbG(new BigDecimal("30"))
                .maxNetCarbG(new BigDecimal("68")).maxGl(new BigDecimal("24")).build()));
        when(weights.findFirstByIsDefaultTrue()).thenReturn(Optional.of(SolverWeightProfile.builder().build()));
        when(catalog.fetchCandidatesForSolver(any(),any(),anySet(),anySet(),anySet())).thenReturn(List.of(original,replacement));
        request=new CheckedMealChangeRequest(); request.setExpectedVersion(0L); request.setItemId(11L);
        request.setNewDishId(2L); request.setNewServingScaledX2(3);
    }
    @AfterEach void shutdown() { executor.shutdown(); }

    DishSolverDto dish(Long id,long carb) {
        return DishSolverDto.builder().dishId(id).code("D"+id).nameVi("Dish "+id)
            .role(DishRole.COMPOSITE_DISH).ingredientGroup(IngredientGroup.RICE_GRAIN)
            .validMealSlots(Set.of(MealSlot.BREAKFAST)).caloriesX10(4000).netCarbX10(carb)
            .proteinX10(200).fatX10(100).fiberX10(60).glX10(100).sodiumX10(1000).cholesterolX10(100)
            .minServingX2(1).maxServingX2(6).stepServingX2(1).householdUnitLabel("1 bowl")
            .rawIngredientsPerServing(Map.of(id,DishSolverDto.RawIngredientNeedDto.builder()
                .ingredientId(id).ingredientNameVi("Ingredient").rawWeightG(new BigDecimal("100")).build())).build();
    }
    void rejected(HttpStatus status,Runnable action) {
        assertEquals(status,assertThrows(OptimizerBusinessException.class,action::run).getStatus());
        assertEquals(1L,plan.getItems().getFirst().getDishId());
        assertEquals(2,plan.getItems().getFirst().getServingScaledX2());
        verify(plans,never()).saveAndFlush(any());
    }
    @Test void previewPinsPortionsAndLeavesStoredPlanUntouched() {
        var result=service.preview(99L,7L,request);
        assertTrue(result.isValidationPassed()); assertEquals(64,result.getChangeSignature().length());
        assertEquals(3,result.getMealsBySlot().get(MealSlot.BREAKFAST).getFirst().getServingScaledX2());
        assertEquals(0,new BigDecimal("600").compareTo(result.getActualCaloriesKcal()));
        assertEquals(1L,plan.getItems().getFirst().getDishId()); verify(plans,never()).saveAndFlush(any());
    }
    @Test void applyRevalidatesAndWritesOnlyConfirmedChange() {
        request.setPreviewSignature(service.preview(99L,7L,request).getChangeSignature());
        var result=service.apply(99L,7L,request);
        assertTrue(result.isValidationPassed()); assertEquals(1L,result.getVersion());
        assertEquals(2L,plan.getItems().getFirst().getDishId());
        assertEquals(3,plan.getItems().getFirst().getServingScaledX2());
        verify(plans).saveAndFlush(plan);
    }
    @Test void infeasiblePortionIsNotSaved() {
        request.setNewServingScaledX2(4); // 90 g carbs exceeds this meal's hard limit.
        rejected(HttpStatus.UNPROCESSABLE_ENTITY,()->service.preview(99L,7L,request));
    }
    @Test void staleVersionIsNotSaved() {
        request.setExpectedVersion(5L); rejected(HttpStatus.CONFLICT,()->service.apply(99L,7L,request));
    }
    @Test void lockedDishIsNotChanged() {
        plan.getItems().getFirst().setIsLocked(true); rejected(HttpStatus.CONFLICT,()->service.preview(99L,7L,request));
    }
    @Test void completedDishIsNotChanged() {
        plan.getItems().getFirst().setStatus(MealItemStatus.COMPLETED);
        rejected(HttpStatus.CONFLICT,()->service.preview(99L,7L,request));
    }
    @Test void changedCatalogRequiresAnotherPreview() {
        request.setPreviewSignature(service.preview(99L,7L,request).getChangeSignature());
        replacement.setCaloriesX10(4200);
        rejected(HttpStatus.CONFLICT,()->service.apply(99L,7L,request));
    }
    @Test void missingPreviewDoesNotWrite() {
        rejected(HttpStatus.CONFLICT,()->service.apply(99L,7L,request));
    }
    @Test void wrongOwnerCannotReadPlan() {
        rejected(HttpStatus.NOT_FOUND,()->service.preview(100L,7L,request));
    }
    @Test void legacyPolicyMustNotBeGuessed() {
        plan.setChangePolicyRecorded(false); rejected(HttpStatus.CONFLICT,()->service.preview(99L,7L,request));
    }
    @Test void otherMealKeepsItsDishPortionAndSnapshot() {
        DishSolverDto other=dish(3L,400);
        other.setValidMealSlots(Set.of(MealSlot.BREAKFAST,MealSlot.DINNER));
        MealPlanItem untouched=new MealPlanItem(); untouched.setId(12L); untouched.setMealSlot(MealSlot.DINNER);
        untouched.setIsLocked(true); untouched.setStatus(MealItemStatus.PLANNED);
        CheckedMealChangeService.writeItem(untouched,other,2);
        plan.getItems().add(untouched); plan.recalculateTotalsFromItems();
        var templateRepo=mock(MealSlotTemplateRepository.class);
        when(templateRepo.findByTemplateCodeOrderByIdAsc("STANDARD_4_MEALS")).thenReturn(
            List.of(MealSlot.BREAKFAST,MealSlot.DINNER).stream().map(slot -> MealSlotTemplate.builder()
                .mealSlot(slot).allowCompositeDish(true).calorieRatioPct(new BigDecimal("50"))
                .minNetCarbG(new BigDecimal("30")).maxNetCarbG(new BigDecimal("68"))
                .maxGl(new BigDecimal("24")).build()).toList());
        var weightRepo=mock(SolverWeightProfileRepository.class);
        when(weightRepo.findFirstByIsDefaultTrue()).thenReturn(Optional.of(SolverWeightProfile.builder().build()));
        when(catalog.fetchCandidatesForSolver(any(),any(),anySet(),anySet(),anySet())).thenReturn(List.of(original,replacement,other));
        service=new CheckedMealChangeService(plans,templateRepo,weightRepo,catalog,new CpSatMealOptimizationEngine(),executor);
        request.setPreviewSignature(service.preview(99L,7L,request).getChangeSignature());
        service.apply(99L,7L,request);
        assertSame(untouched,plan.getItems().get(1));
        assertEquals(3L,untouched.getDishId()); assertEquals(2,untouched.getServingScaledX2());
        assertTrue(untouched.getIsLocked());
        assertEquals(0,new BigDecimal("400").compareTo(untouched.getSnapshotCaloriesKcal()));
    }
    @Test void currentExclusionsAreSentToCatalog() {
        request.setExcludedDishIds(Set.of(8L)); request.setContraindications(Set.of(MedicalTag.ALLERGEN_EGG));
        service.preview(99L,7L,request);
        verify(catalog).fetchCandidatesForSolver(eq(99L),any(),eq(Set.of(MedicalTag.ALLERGEN_EGG)),eq(Set.of(8L)),eq(Set.of(MealSlot.BREAKFAST)));
    }
}
