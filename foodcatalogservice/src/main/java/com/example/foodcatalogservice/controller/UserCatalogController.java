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
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class UserCatalogController {

    private final FoodCatalogService catalogService;

    @GetMapping("/dishes")
    public ResponseEntity<Page<DishDetailResponse>> searchDishes(
            @RequestHeader(value = "X-User-Id", required = false) Long userId,
            @RequestParam(required = false) DishRole role,
            @RequestParam(required = false) MealSlot slot,
            @RequestParam(required = false) GiLevel giLevel,
            @RequestParam(required = false, defaultValue = "") String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ResponseEntity.ok(catalogService.searchDishesForUser(userId, role, slot, giLevel, keyword, page, size));
    }

    @GetMapping("/dishes/{id}")
    public ResponseEntity<DishDetailResponse> getDishDetail(@PathVariable Long id) {
        return ResponseEntity.ok(catalogService.getDishDetail(id));
    }

    @PostMapping("/users/me/dishes/{dishId}/favorite")
    public ResponseEntity<Void> markFavorite(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long dishId) {
        catalogService.setUserDishPreference(userId, dishId, PreferenceType.FAVORITE);
        return ResponseEntity.ok().build();
    }

    @PostMapping("/users/me/dishes/{dishId}/dislike")
    public ResponseEntity<Void> markDislike(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable Long dishId) {
        catalogService.setUserDishPreference(userId, dishId, PreferenceType.DISLIKE);
        return ResponseEntity.ok().build();
    }

    @GetMapping("/users/me/food-preferences")
    public ResponseEntity<UserPreferenceResponse> getUserPreferences(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) {
        return ResponseEntity.ok(catalogService.getUserPreferences(userId));
    }

    @GetMapping("/dishes/{id}/calculate-serving")
    public ResponseEntity<DynamicServingResponse> calculateDynamicServing(
            @PathVariable Long id,
            @RequestParam(defaultValue = "1.0") BigDecimal multiplier) {
        return ResponseEntity.ok(catalogService.calculateDynamicServing(id, multiplier));
    }

    @PostMapping("/dishes/{id}/safety-check")
    public ResponseEntity<SafetyCheckResponse> checkPersonalizedSafety(
            @PathVariable Long id,
            @RequestBody @Valid SafetyCheckRequest req) {
        return ResponseEntity.ok(catalogService.checkPersonalizedSafety(id, req));
    }

    @GetMapping("/dishes/{id}/alternatives")
    public ResponseEntity<List<DishDetailResponse>> getAlternatives(
            @PathVariable Long id,
            @RequestParam(required = false) MealSlot mealSlot) {
        return ResponseEntity.ok(catalogService.findAlternatives(id, mealSlot));
    }

    @GetMapping("/dishes/compare")
    public ResponseEntity<DishComparisonResponse> compareDishes(
            @RequestParam Long dish1,
            @RequestParam Long dish2) {
        return ResponseEntity.ok(catalogService.compareTwoDishes(dish1, dish2));
    }

    @PostMapping("/users/me/custom-dishes")
    public ResponseEntity<DishDetailResponse> createCustomFamilyDish(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @RequestBody @Valid CreateDishRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(catalogService.createDish(req, userId));
    }
}
