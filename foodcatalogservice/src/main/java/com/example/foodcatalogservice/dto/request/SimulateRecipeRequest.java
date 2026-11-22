package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import jakarta.validation.*;
import lombok.*;
import jakarta.validation.constraints.*;

import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SimulateRecipeRequest {
    @NotNull private CookingMethod cookingMethod;
    @NotEmpty @Valid
    private List<RecipeItemRequest> recipeItems;
}
