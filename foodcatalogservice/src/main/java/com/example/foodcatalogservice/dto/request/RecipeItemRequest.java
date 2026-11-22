package com.example.foodcatalogservice.dto.request;
import lombok.*;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RecipeItemRequest {
    @NotNull private Long ingredientId;
    @NotNull @DecimalMin("0.1") private BigDecimal rawWeightG;
    private boolean isMainIngredient;
}
