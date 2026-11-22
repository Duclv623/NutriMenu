package com.example.foodcatalogservice.dto.response;
import lombok.*;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DishComparisonResponse {
    private DishDetailResponse dish1;
    private DishDetailResponse dish2;
    private BigDecimal netCarbDiffG;
    private BigDecimal fiberDiffG;
    private BigDecimal giDiff;
    private BigDecimal glDiff;
    private Long recommendedDishIdForDiabetic;
    private String comparisonSummaryVi;
}
