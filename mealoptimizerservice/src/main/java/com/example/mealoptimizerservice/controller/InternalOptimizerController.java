package com.example.mealoptimizerservice.controller;

import com.example.mealoptimizerservice.dto.*;
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
import java.util.Map;
import java.util.Set;
import com.example.mealoptimizerservice.dto.request.*;
import com.example.mealoptimizerservice.dto.response.*;

// --- FILE: InternalOptimizerController.java ---
@RestController
@RequestMapping("/api/v1/internal/optimizer")
@RequiredArgsConstructor
public class InternalOptimizerController {

    private final MealOptimizerService optimizerService;

    @GetMapping("/users/{userId}/recent-dishes")
    public ResponseEntity<Set<Long>> getRecentDishes(
            @PathVariable Long userId,
            @RequestParam(defaultValue = "3") int days) {
        return ResponseEntity.ok(optimizerService.getRecentEatenDishIds(userId, days));
    }

    @PostMapping("/feasibility-check")
    public ResponseEntity<InfeasibilityDiagnosisResponse> quickFeasibilityCheck(
            @RequestBody @Valid GenerateDailyMealRequest req) {
        return ResponseEntity.ok(optimizerService.explainInfeasibility(req));
    }
}
