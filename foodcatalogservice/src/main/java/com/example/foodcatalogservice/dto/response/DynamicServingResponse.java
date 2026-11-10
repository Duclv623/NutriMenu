package com.example.foodcatalogservice.dto.response;
import com.example.foodcatalogservice.dto.RecipeIngredientBreakdownDto;
import com.example.foodcatalogservice.entity.enums.TrafficLightBadge;
import lombok.*;

import java.math.BigDecimal;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DynamicServingResponse {
    private Long dishId;
    private String dishNameVi;
    private BigDecimal multiplier;
    private String adjustedHouseholdLabel;
    private BigDecimal adjustedCookedWeightG;
    private BigDecimal caloriesKcal;
    private BigDecimal netCarbG;
    private BigDecimal fiberG;
    private BigDecimal proteinG;
    private BigDecimal fatG;
    private BigDecimal sodiumMg;
    private BigDecimal estimatedGi;
    private BigDecimal adjustedGlycemicLoad;
    private TrafficLightBadge adjustedBadge;
    private boolean isGlExceededWarning;
    private String medicalWarningMessage;
    private List<RecipeIngredientBreakdownDto> adjustedIngredients;
}
