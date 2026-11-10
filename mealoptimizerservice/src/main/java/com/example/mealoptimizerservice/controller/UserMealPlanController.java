package com.example.mealoptimizerservice.controller;

import com.example.mealoptimizerservice.dto.*;
import com.example.mealoptimizerservice.dto.request.*;
import com.example.mealoptimizerservice.dto.response.*;
import com.example.mealoptimizerservice.entity.*;
import com.example.mealoptimizerservice.service.MealOptimizerService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;

// --- FILE: UserMealPlanController.java ---
@RestController
@RequestMapping("/api/v1/users/me/meal-plans")
@RequiredArgsConstructor
public class UserMealPlanController {

    private final MealOptimizerService optimizerService;

    @GetMapping
    public ResponseEntity<Page<MealPlanResponse>> getMyMealPlans(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return ResponseEntity.ok(optimizerService.getUserMealPlans(userId, page, size));
    }

    @GetMapping("/{planId}")
    public ResponseEntity<MealPlanResponse> getMealPlanDetail(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId) {
        return ResponseEntity.ok(optimizerService.getMealPlanDetail(userId, planId));
    }

    @DeleteMapping("/{planId}")
    public ResponseEntity<Void> deleteMealPlan(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId) {
        optimizerService.deleteMealPlan(userId, planId);
        return ResponseEntity.noContent().build();
    }

    @PatchMapping("/{planId}/items/{itemId}/status")
    public ResponseEntity<MealPlanResponse> updateMealItemStatus(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @PathVariable Long itemId,
            @RequestBody @Valid UpdateMealItemStatusRequest req) {
        return ResponseEntity.ok(optimizerService.updateMealItemStatus(userId, planId, itemId, req.getStatus()));
    }

    @PatchMapping("/{planId}/items/{itemId}/lock")
    public ResponseEntity<MealPlanResponse> toggleLockItem(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @PathVariable Long itemId,
            @RequestBody @Valid LockMealItemRequest req) {
        return ResponseEntity.ok(optimizerService.toggleMealItemLock(userId, planId, itemId, req.getIsLocked()));
    }

    @PostMapping("/{planId}/rate")
    public ResponseEntity<MealPlanResponse> rateMealPlan(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @RequestBody @Valid RateMealPlanRequest req) {
        return ResponseEntity.ok(optimizerService.rateMealPlan(userId, planId, req));
    }

    @GetMapping("/shopping-list")
    public ResponseEntity<ShoppingListResponse> getShoppingList(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate fromDate,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate toDate) {
        return ResponseEntity.ok(optimizerService.generateSmartShoppingList(userId, fromDate, toDate));
    }

    @PutMapping("/{planId}/items/{itemId}/manual-replace")
    public ResponseEntity<MealPlanResponse> manualReplaceItem(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @PathVariable Long itemId,
            @RequestBody @Valid ManualReplaceItemRequest req) {
        return ResponseEntity.ok(optimizerService.manualReplaceMealItem(userId, planId, itemId, req));
    }

    @GetMapping("/analytics")
    public ResponseEntity<NutritionalAnalyticsResponse> getAnalytics(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestParam(defaultValue = "7") int days) {
        return ResponseEntity.ok(optimizerService.getNutritionalAnalytics(userId, days));
    }

    @PostMapping("/generate-daily")
    public ResponseEntity<MealPlanResponse> generateDaily(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestBody @Valid GenerateDailyMealRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(optimizerService.generateOptimalDailyMealPlan(userId, req));
    }

    @PostMapping("/{planId}/swap-dish")
    public ResponseEntity<MealPlanResponse> swapSingleDish(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @RequestBody @Valid SwapSingleDishRequest req) {
        return ResponseEntity.ok(optimizerService.swapSingleDishInPlan(userId, planId, req));
    }

    @PostMapping("/{planId}/rebalance-remaining")
    public ResponseEntity<MealPlanResponse> rebalanceRemaining(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long planId,
            @RequestBody @Valid RebalanceRemainingMealsRequest req) {
        return ResponseEntity.ok(optimizerService.rebalanceRemainingMeals(userId, planId, req));
    }

    @PostMapping("/generate-weekly")
    public ResponseEntity<List<MealPlanResponse>> generateWeekly(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestBody @Valid GenerateWeeklyMealRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(optimizerService.generateWeeklyMealPlans(userId, req));
    }
}
