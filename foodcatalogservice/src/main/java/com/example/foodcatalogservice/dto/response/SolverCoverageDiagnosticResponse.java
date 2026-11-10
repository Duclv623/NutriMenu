package com.example.foodcatalogservice.dto.response;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import lombok.*;

import java.util.List;
import java.util.Map;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SolverCoverageDiagnosticResponse {
    private boolean isSolverReady;
    private int totalEligibleDishes;
    private Map<MealSlot, Map<DishRole, Integer>> slotRoleMatrix;
    private List<String> bottleneckWarnings;
}
