package com.example.foodcatalogservice.controller;

import com.example.foodcatalogservice.dto.request.*;
import com.example.foodcatalogservice.dto.response.*;
import com.example.foodcatalogservice.entity.Ingredient;
import com.example.foodcatalogservice.entity.YieldRetentionFactor;
import com.example.foodcatalogservice.entity.enums.*;
import com.example.foodcatalogservice.service.FoodCatalogService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;

@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class AdminCatalogController {

    private final FoodCatalogService catalogService;

    @PostMapping("/ingredients")
    public ResponseEntity<Ingredient> createIngredient(@RequestBody @Valid UpsertIngredientRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(catalogService.createIngredient(req));
    }

    @PutMapping("/ingredients/{id}")
    public ResponseEntity<Ingredient> updateIngredient(
            @PathVariable Long id, @RequestBody @Valid UpsertIngredientRequest req) {
        return ResponseEntity.ok(catalogService.updateIngredientAndCascade(id, req));
    }

    @GetMapping("/ingredients")
    public ResponseEntity<Page<Ingredient>> searchIngredients(
            @RequestParam(required = false) IngredientGroup group,
            @RequestParam(required = false) GiLevel giLevel,
            @RequestParam(required = false, defaultValue = "") String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(catalogService.searchIngredients(group, giLevel, keyword, page, size));
    }

    @DeleteMapping("/ingredients/{id}")
    public ResponseEntity<Void> deleteIngredient(@PathVariable Long id) {
        catalogService.deleteIngredientSafely(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/yield-factors")
    public ResponseEntity<List<YieldRetentionFactor>> getYieldFactors() {
        return ResponseEntity.ok(catalogService.getAllYieldFactors());
    }

    @PostMapping("/yield-factors")
    public ResponseEntity<YieldRetentionFactor> createYieldFactor(@RequestBody @Valid UpsertYieldFactorRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(catalogService.upsertYieldFactor(req));
    }

    @PatchMapping("/dishes/{id}/status")
    public ResponseEntity<DishDetailResponse> updateDishStatus(
            @PathVariable Long id, @RequestBody @Valid UpdateDishStatusRequest req) {
        return ResponseEntity.ok(catalogService.updateDishStatus(id, req.getIsActive()));
    }

    @PatchMapping("/dishes/{id}/popularity")
    public ResponseEntity<DishDetailResponse> updateDishPopularity(
            @PathVariable Long id, @RequestBody @Valid UpdatePopularityRequest req) {
        return ResponseEntity.ok(catalogService.updateDishPopularity(id, req.getPopularityScore()));
    }

    @PutMapping("/dishes/{id}/serving-rules")
    public ResponseEntity<DishDetailResponse> updateServingRules(
            @PathVariable Long id, @RequestBody @Valid UpdateServingRulesRequest req) {
        return ResponseEntity.ok(catalogService.updateServingRules(id, req));
    }

    @PutMapping("/dishes/{id}/medical-tags")
    public ResponseEntity<DishDetailResponse> overrideMedicalTags(
            @PathVariable Long id, @RequestBody @Valid OverrideMedicalTagsRequest req) {
        return ResponseEntity.ok(catalogService.overrideMedicalTags(id, req));
    }

    @PostMapping("/ingredients/bulk-import")
    public ResponseEntity<BulkImportReportResponse> bulkImportIngredients(
            @RequestBody @NotEmpty List<@Valid UpsertIngredientRequest> items) {
        return ResponseEntity.ok(catalogService.bulkImportIngredients(items));
    }

    @PostMapping("/dishes/simulate-nutrition")
    public ResponseEntity<SimulationResultResponse> simulateRecipeNutrition(
            @RequestBody @Valid SimulateRecipeRequest req) {
        return ResponseEntity.ok(catalogService.simulateRecipeNutrition(req));
    }

    @PostMapping("/dishes")
    public ResponseEntity<DishDetailResponse> createDish(@RequestBody @Valid CreateDishRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(catalogService.createDish(req, null));
    }

    @PutMapping("/dishes/{id}")
    public ResponseEntity<DishDetailResponse> updateDish(
            @PathVariable Long id, @RequestBody @Valid CreateDishRequest req) {
        return ResponseEntity.ok(catalogService.updateDish(id, req));
    }

    @PostMapping("/ingredients/{id}/recalculate-affected-dishes")
    public ResponseEntity<CascadeRecalculationResponse> recalculateAffectedDishes(@PathVariable Long id) {
        return ResponseEntity.ok(catalogService.recalculateDishesContainingIngredient(id));
    }

    @PostMapping("/diagnostics/solver-coverage")
    public ResponseEntity<SolverCoverageDiagnosticResponse> analyzeSolverCoverage(
            @RequestBody @Valid SolverCoverageDiagnosticRequest req) {
        return ResponseEntity.ok(catalogService.analyzeSolverCoverage(req));
    }
}
