package com.example.foodcatalogservice.service;

import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class PreparationGuideTest {
    @Test void usesRealIngredientWeightsAndDisclosesMethodBasedGuide() {
        Dish dish=new Dish(); dish.setCookingMethod(CookingMethod.SOUP_SIMMERED);
        dish.setIngredients(List.of(DishIngredient.builder()
            .ingredient(Ingredient.builder().nameVi("Cà rốt").build()).rawWeightG(new BigDecimal("45.00")).build()));
        var steps=PreparationGuide.steps(dish);
        assertTrue(steps.getFirst().contains("Cà rốt: 45 g"));
        assertTrue(steps.stream().anyMatch(s->s.contains("ninh")));
        assertTrue(steps.getLast().contains("chưa có công thức nấu hoàn chỉnh"));
    }
    @Test void missingRecipeDoesNotInventInstructions() {
        Dish dish=new Dish(); dish.setCookingMethod(CookingMethod.BOILED);
        assertTrue(PreparationGuide.steps(dish).isEmpty());
    }
}
