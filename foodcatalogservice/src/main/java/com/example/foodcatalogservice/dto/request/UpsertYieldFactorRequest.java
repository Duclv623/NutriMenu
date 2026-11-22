package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import jakarta.validation.constraints.*;
import lombok.*;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UpsertYieldFactorRequest {
    private Long ingredientId;
    @NotNull private IngredientGroup ingredientGroup;
    @NotNull private CookingMethod cookingMethod;
    @NotNull @DecimalMin("0.1") private BigDecimal yieldFactor;
    @NotNull @DecimalMin("0.0") private BigDecimal oilAbsorptionPct;
}
