package com.example.mealoptimizerservice.controller;

import com.example.mealoptimizerservice.dto.request.CheckedMealChangeRequest;
import com.example.mealoptimizerservice.dto.response.MealPlanResponse;
import com.example.mealoptimizerservice.service.CheckedMealChangeService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController @RequiredArgsConstructor
@RequestMapping("/api/v1/users/me/meal-plans/{planId}")
public class CheckedMealChangeController {
    private final CheckedMealChangeService changes;
    @PostMapping("/change-preview")
    public MealPlanResponse preview(@RequestHeader("X-User-Id") Long user, @PathVariable Long planId,
                                   @RequestBody @Valid CheckedMealChangeRequest request) { return changes.preview(user,planId,request); }
    @PostMapping("/change-apply")
    public MealPlanResponse apply(@RequestHeader("X-User-Id") Long user, @PathVariable Long planId,
                                 @RequestBody @Valid CheckedMealChangeRequest request) { return changes.apply(user,planId,request); }
}
