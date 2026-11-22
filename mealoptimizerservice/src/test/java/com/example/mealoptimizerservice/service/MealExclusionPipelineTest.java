package com.example.mealoptimizerservice.service;

import com.example.mealoptimizerservice.client.FoodCatalogIntegrationClient;
import com.example.mealoptimizerservice.dto.request.GenerateDailyMealRequest;
import com.example.mealoptimizerservice.entity.MealSlotTemplate;
import com.example.mealoptimizerservice.entity.enums.MealSlot;
import com.example.mealoptimizerservice.repository.*;
import com.example.mealoptimizerservice.solver.CpSatMealOptimizationEngine;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MealExclusionPipelineTest {
    private static class StopAtCatalog extends RuntimeException {}

    private void verifyExclusions(Set<Long> explicit, Set<Long> recent, Set<Long> expected) {
        MealSlotTemplateRepository templates = mock(MealSlotTemplateRepository.class);
        FoodCatalogIntegrationClient catalog = mock(FoodCatalogIntegrationClient.class);
        when(templates.findByTemplateCodeOrderByIdAsc("STANDARD_4_MEALS"))
                .thenReturn(List.of(MealSlotTemplate.builder().mealSlot(MealSlot.BREAKFAST).build()));
        when(catalog.fetchCandidatesForSolver(any(), any(), any(), any(), any()))
                .thenThrow(new StopAtCatalog());
        MealOptimizerService service = new MealOptimizerService(
                mock(SolverWeightProfileRepository.class), templates, mock(MealPlanRepository.class),
                mock(CuratedFallbackPlanRepository.class), mock(SolverAuditLogRepository.class), catalog,
                mock(CpSatMealOptimizationEngine.class), mock(DiabeticClinicalTargetCalculator.class),
                mock(ThreadPoolTaskExecutor.class));
        GenerateDailyMealRequest request = GenerateDailyMealRequest.builder().excludedDishIds(explicit).build();
        assertThrows(StopAtCatalog.class, () -> ReflectionTestUtils.invokeMethod(service,
                "runOptimizationPipelineWithExtraExclusions", 12L, request, recent, false, "TEST"));
        verify(catalog).fetchCandidatesForSolver(eq(12L), any(), any(), eq(expected), eq(Set.of(MealSlot.BREAKFAST)));
    }

    @Test
    void explicitExclusionsAreMergedWithRecentDishesBeforeCatalogSelection() {
        verifyExclusions(Set.of(4L, 8L), Set.of(8L, 9L), Set.of(4L, 8L, 9L));
    }

    @Test
    void callersWithoutExplicitExclusionsKeepExistingBehavior() {
        verifyExclusions(Set.of(), Set.of(9L), Set.of(9L));
    }
}
