package com.example.foodcatalogservice.dto.response;
import com.example.foodcatalogservice.dto.RecipeIngredientBreakdownDto;
import com.example.foodcatalogservice.entity.Dish;
import com.example.foodcatalogservice.entity.enums.*;
import lombok.*;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.List;
import java.util.Set;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DishDetailResponse {
    private Long id;
    private String code;
    private String nameVi;
    private String imageUrl;
    private String diabeticCookingTip;
    private DishRole role;
    private CookingMethod cookingMethod;
    private IngredientGroup primaryIngredientGroup;
    private BigDecimal standardServingCookedG;
    private String householdUnitLabel;
    private BigDecimal caloriesKcal;
    private BigDecimal totalCarbG;
    private BigDecimal fiberG;
    private BigDecimal netCarbG;
    private BigDecimal proteinG;
    private BigDecimal fatG;
    private BigDecimal saturatedFatG;
    private BigDecimal sodiumMg;
    private BigDecimal potassiumMg;
    private BigDecimal purineMg;
    private BigDecimal estimatedGi;
    private GiLevel giLevel;
    private BigDecimal glycemicLoad;
    private TrafficLightBadge trafficLightBadge;
    private Set<MealSlot> mealSlots;
    private Set<MedicalTag> medicalTags;
    private Long createdByUserId;
    private List<RecipeIngredientBreakdownDto> recipeBreakdown;

    public static DishDetailResponse fromEntity(Dish d, boolean includeBreakdown) {
        List<RecipeIngredientBreakdownDto> breakdown = includeBreakdown && d.getIngredients() != null
                ? d.getIngredients().stream().map(di -> RecipeIngredientBreakdownDto.builder()
                .ingredientId(di.getIngredient().getId())
                .ingredientNameVi(di.getIngredient().getNameVi())
                .rawWeightG(di.getRawWeightG())
                .appliedYieldFactor(di.getAppliedYieldFactor())
                .cookedWeightG(di.getCookedWeightG())
                .isMainIngredient(Boolean.TRUE.equals(di.getIsMainIngredient()))
                .build()).toList()
                : Collections.emptyList();

        return DishDetailResponse.builder()
                .id(d.getId())
                .code(d.getCode())
                .nameVi(d.getNameVi())
                .imageUrl(d.getImageUrl())
                .diabeticCookingTip(d.getDiabeticCookingTip())
                .role(d.getDishRole())
                .cookingMethod(d.getCookingMethod())
                .primaryIngredientGroup(d.getPrimaryIngredientGroup())
                .standardServingCookedG(d.getStandardServingCookedG())
                .householdUnitLabel(d.getHouseholdUnitLabel())
                .caloriesKcal(d.getCaloriesKcal())
                .totalCarbG(d.getTotalCarbG())
                .fiberG(d.getFiberG())
                .netCarbG(d.getNetCarbG())
                .proteinG(d.getProteinG())
                .fatG(d.getFatG())
                .saturatedFatG(d.getSaturatedFatG())
                .sodiumMg(d.getSodiumMg())
                .potassiumMg(d.getPotassiumMg())
                .purineMg(d.getPurineMg())
                .estimatedGi(d.getEstimatedGi())
                .giLevel(d.getGiLevel())
                .glycemicLoad(d.getGlycemicLoad())
                .trafficLightBadge(TrafficLightBadge.evaluate(d.getEstimatedGi(), d.getGlycemicLoad()))
                .mealSlots(d.getMealSlots())
                .medicalTags(d.getMedicalTags())
                .createdByUserId(d.getCreatedByUserId())
                .recipeBreakdown(breakdown)
                .build();
    }
}
