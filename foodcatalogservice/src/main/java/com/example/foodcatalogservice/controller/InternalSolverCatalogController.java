package com.example.foodcatalogservice.controller;

import com.example.foodcatalogservice.dto.DishSolverDto;
import com.example.foodcatalogservice.dto.request.*;
import com.example.foodcatalogservice.dto.response.*;
import com.example.foodcatalogservice.service.FoodCatalogService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/internal/dishes")
@RequiredArgsConstructor
public class InternalSolverCatalogController {

    private final FoodCatalogService catalogService;

    @PostMapping("/candidates")
    public ResponseEntity<List<DishSolverDto>> getCandidatesForSolver(
            @RequestBody @Valid CandidateFilterRequest request) {
        return ResponseEntity.ok(catalogService.getCandidateDishesForSolver(request));
    }

    @GetMapping("/{id}/solver-dto")
    public ResponseEntity<DishSolverDto> getSingleSolverDto(@PathVariable Long id) {
        return ResponseEntity.ok(catalogService.getSingleSolverDto(id));
    }

    @PostMapping("/batch")
    public ResponseEntity<List<DishDetailResponse>> getBatchDishes(
            @RequestBody @NotEmpty List<Long> dishIds) {
        return ResponseEntity.ok(catalogService.getBatchDetails(dishIds));
    }
}
