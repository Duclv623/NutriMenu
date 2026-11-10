package com.example.foodcatalogservice.config;

import com.example.foodcatalogservice.dto.request.CreateDishRequest;
import com.example.foodcatalogservice.dto.request.RecipeItemRequest;
import com.example.foodcatalogservice.dto.request.UpsertIngredientRequest;
import com.example.foodcatalogservice.entity.Ingredient;
import com.example.foodcatalogservice.entity.YieldRetentionFactor;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import com.example.foodcatalogservice.repository.DishRepository;
import com.example.foodcatalogservice.repository.YieldFactorRepository;
import com.example.foodcatalogservice.service.FoodCatalogService;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;

@Configuration
@RequiredArgsConstructor
public class CatalogDataSeederConfig {

    private final YieldFactorRepository yrfRepo;
    private final DishRepository dishRepo;
    private final FoodCatalogService catalogService;

    @Bean
    public CommandLineRunner seedVietnameseDiabeticCatalog() {
        return args -> {
            if (dishRepo.count() > 0) return;

            yrfRepo.saveAll(List.of(
                    YieldRetentionFactor.builder()
                            .ingredientGroup(IngredientGroup.RICE_GRAIN)
                            .cookingMethod(CookingMethod.BOILED)
                            .yieldFactor(new BigDecimal("2.400"))
                            .oilAbsorptionPct(BigDecimal.ZERO)
                            .build(),
                    YieldRetentionFactor.builder()
                            .ingredientGroup(IngredientGroup.POULTRY)
                            .cookingMethod(CookingMethod.BRAISED)
                            .yieldFactor(new BigDecimal("0.750"))
                            .oilAbsorptionPct(new BigDecimal("2.00"))
                            .build(),
                    YieldRetentionFactor.builder()
                            .ingredientGroup(IngredientGroup.LEAFY_VEG)
                            .cookingMethod(CookingMethod.BOILED)
                            .yieldFactor(new BigDecimal("0.900"))
                            .oilAbsorptionPct(BigDecimal.ZERO)
                            .build()
            ));

            Ingredient brownRice = catalogService.createIngredient(UpsertIngredientRequest.builder()
                    .vfcCode("VFC_G002")
                    .nameVi("Gạo lứt tẻ")
                    .ingredientGroup(IngredientGroup.RICE_GRAIN)
                    .ediblePortionPct(new BigDecimal("100.0"))
                    .caloriesPer100g(new BigDecimal("345.0"))
                    .totalCarbG(new BigDecimal("72.8"))
                    .fiberG(new BigDecimal("3.4"))
                    .proteinG(new BigDecimal("7.5"))
                    .fatG(new BigDecimal("2.7"))
                    .saturatedFatG(new BigDecimal("0.6"))
                    .sodiumMg(new BigDecimal("5.0"))
                    .potassiumMg(new BigDecimal("220.0"))
                    .purineMg(new BigDecimal("35.0"))
                    .giValue(new BigDecimal("50.0"))
                    .allergenTags(Set.of())
                    .build());

            Ingredient chickenBreast = catalogService.createIngredient(UpsertIngredientRequest.builder()
                    .vfcCode("VFC_T015")
                    .nameVi("Ức gà không da")
                    .ingredientGroup(IngredientGroup.POULTRY)
                    .ediblePortionPct(new BigDecimal("100.0"))
                    .caloriesPer100g(new BigDecimal("120.0"))
                    .totalCarbG(BigDecimal.ZERO)
                    .fiberG(BigDecimal.ZERO)
                    .proteinG(new BigDecimal("22.5"))
                    .fatG(new BigDecimal("2.6"))
                    .saturatedFatG(new BigDecimal("0.8"))
                    .sodiumMg(new BigDecimal("65.0"))
                    .potassiumMg(new BigDecimal("250.0"))
                    .purineMg(new BigDecimal("130.0"))
                    .giValue(BigDecimal.ZERO)
                    .allergenTags(Set.of())
                    .build());

            catalogService.createDish(CreateDishRequest.builder()
                    .code("STARCH_BROWN_RICE")
                    .nameVi("Cơm gạo lứt hấp mềm")
                    .imageUrl("https://placehold.co/400x300/e8f5e9/1b5e20?text=Com+Gao+Lut")
                    .diabeticCookingTip("Ngâm gạo lứt 2 tiếng trước khi nấu để hạt cơm mềm và giàu chất xơ.")
                    .cookingMethod(CookingMethod.BOILED)
                    .dishRole(DishRole.MAIN_STARCH)
                    .householdUnitLabel("1 lưng bát con (120g)")
                    .mealSlots(Set.of(MealSlot.LUNCH, MealSlot.DINNER))
                    .minServingScaledX2(1)
                    .maxServingScaledX2(3)
                    .stepServingScaledX2(1)
                    .recipeItems(List.of(RecipeItemRequest.builder()
                            .ingredientId(brownRice.getId())
                            .rawWeightG(new BigDecimal("50.0"))
                            .isMainIngredient(true)
                            .build()))
                    .build(), null);

            catalogService.createDish(CreateDishRequest.builder()
                    .code("PROT_CHICKEN_GINGER")
                    .nameVi("Ức gà rim gừng ít muối")
                    .imageUrl("https://placehold.co/400x300/fff3e0/e65100?text=Uc+Ga+Rim+Gung")
                    .diabeticCookingTip("Sử dụng gừng tươi tạo vị đậm đà thay vì dùng nhiều nước mắm hay đường.")
                    .cookingMethod(CookingMethod.BRAISED)
                    .dishRole(DishRole.PROTEIN_DISH)
                    .householdUnitLabel("1 đĩa nhỏ (85g)")
                    .mealSlots(Set.of(MealSlot.LUNCH, MealSlot.DINNER))
                    .minServingScaledX2(2)
                    .maxServingScaledX2(3)
                    .stepServingScaledX2(1)
                    .recipeItems(List.of(RecipeItemRequest.builder()
                            .ingredientId(chickenBreast.getId())
                            .rawWeightG(new BigDecimal("110.0"))
                            .isMainIngredient(true)
                            .build()))
                    .build(), null);
        };
    }
}
