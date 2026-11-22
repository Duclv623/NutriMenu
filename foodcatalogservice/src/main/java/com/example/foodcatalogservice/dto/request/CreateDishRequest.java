package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import jakarta.validation.Valid;
import lombok.*;
import jakarta.validation.constraints.*;

import java.util.List;
import java.util.Set;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CreateDishRequest {
    @NotBlank private String code;
    @NotBlank private String nameVi;
    private String imageUrl;
    private String diabeticCookingTip;
    @NotNull private CookingMethod cookingMethod;
    @NotNull private DishRole dishRole;
    @NotBlank private String householdUnitLabel;
    @NotEmpty private Set<MealSlot> mealSlots;
    private Integer minServingScaledX2;
    private Integer maxServingScaledX2;
    private Integer stepServingScaledX2;
    @NotEmpty @Valid
    private List<RecipeItemRequest> recipeItems;
}
