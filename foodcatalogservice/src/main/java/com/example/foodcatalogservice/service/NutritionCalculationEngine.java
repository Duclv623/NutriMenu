package com.example.foodcatalogservice.service;

import com.example.foodcatalogservice.dto.request.*;
import com.example.foodcatalogservice.dto.response.*;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.*;
import com.example.foodcatalogservice.exception.BusinessRuleException;
import com.example.foodcatalogservice.exception.ResourceNotFoundException;
import com.example.foodcatalogservice.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.Normalizer;
import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class NutritionCalculationEngine {

    private final YieldFactorRepository yieldFactorRepository;

    public void computeNutritionAndMedicalTags(Dish dish, List<DishIngredient> items) {
        BigDecimal totalCookedWeight = BigDecimal.ZERO;
        BigDecimal totalCalories = BigDecimal.ZERO;
        BigDecimal totalCarb = BigDecimal.ZERO;
        BigDecimal totalFiber = BigDecimal.ZERO;
        BigDecimal totalProtein = BigDecimal.ZERO;
        BigDecimal totalFat = BigDecimal.ZERO;
        BigDecimal totalSatFat = BigDecimal.ZERO;
        BigDecimal totalSodium = BigDecimal.ZERO;
        BigDecimal totalPotassium = BigDecimal.ZERO;
        BigDecimal totalPurine = BigDecimal.ZERO;

        BigDecimal weightedGiNumerator = BigDecimal.ZERO;
        BigDecimal totalNetCarbFromIngredients = BigDecimal.ZERO;

        Set<MedicalTag> autoTags = new HashSet<>();
        boolean hasAnimalProduct = false;
        IngredientGroup dominantGroup = IngredientGroup.MIXED;
        BigDecimal maxMainWeight = BigDecimal.ZERO;

        for (DishIngredient item : items) {
            Ingredient ing = item.getIngredient();
            BigDecimal rawG = item.getRawWeightG();
            BigDecimal ratio100 = rawG.divide(new BigDecimal("100.0"), 6, RoundingMode.HALF_UP);

            YieldRetentionFactor yrf = yieldFactorRepository
                    .findByIngredientIdAndCookingMethod(ing.getId(), dish.getCookingMethod())
                    .or(() -> yieldFactorRepository.findByIngredientGroupAndCookingMethodAndIngredientIdIsNull(
                            ing.getIngredientGroup(), dish.getCookingMethod()))
                    .orElse(YieldRetentionFactor.builder()
                            .ingredientGroup(ing.getIngredientGroup())
                            .cookingMethod(dish.getCookingMethod())
                            .yieldFactor(BigDecimal.ONE)
                            .oilAbsorptionPct(BigDecimal.ZERO)
                            .build());

            BigDecimal cookedG = rawG.multiply(yrf.getYieldFactor()).setScale(2, RoundingMode.HALF_UP);
            item.setAppliedYieldFactor(yrf.getYieldFactor());
            item.setCookedWeightG(cookedG);
            totalCookedWeight = totalCookedWeight.add(cookedG);

            if (Boolean.TRUE.equals(item.getIsMainIngredient()) && rawG.compareTo(maxMainWeight) > 0) {
                maxMainWeight = rawG;
                dominantGroup = ing.getIngredientGroup();
            }

            if (EnumSet.of(IngredientGroup.PORK, IngredientGroup.BEEF, IngredientGroup.POULTRY,
                    IngredientGroup.FISH_SEAFOOD, IngredientGroup.EGG).contains(ing.getIngredientGroup())) {
                hasAnimalProduct = true;
            }

            BigDecimal ingCal = ing.getCaloriesPer100g().multiply(ratio100);
            BigDecimal ingFat = ing.getFatG().multiply(ratio100);

            if (yrf.getOilAbsorptionPct().compareTo(BigDecimal.ZERO) > 0) {
                BigDecimal absorbedOilG = rawG.multiply(yrf.getOilAbsorptionPct())
                        .divide(new BigDecimal("100.0"), 4, RoundingMode.HALF_UP);
                ingFat = ingFat.add(absorbedOilG);
                ingCal = ingCal.add(absorbedOilG.multiply(new BigDecimal("9.0")));
            }

            totalCalories = totalCalories.add(ingCal);
            totalCarb = totalCarb.add(ing.getTotalCarbG().multiply(ratio100));
            totalFiber = totalFiber.add(ing.getFiberG().multiply(ratio100));
            totalProtein = totalProtein.add(ing.getProteinG().multiply(ratio100));
            totalFat = totalFat.add(ingFat);
            totalSatFat = totalSatFat.add(ing.getSaturatedFatG().multiply(ratio100));
            totalSodium = totalSodium.add(ing.getSodiumMg().multiply(ratio100));
            totalPotassium = totalPotassium.add(ing.getPotassiumMg().multiply(ratio100));
            totalPurine = totalPurine.add(ing.getPurineMg().multiply(ratio100));

            BigDecimal ingNetCarb = ing.getNetCarbPer100g().multiply(ratio100);
            if (ingNetCarb.compareTo(BigDecimal.ZERO) > 0 && ing.getGiValue().compareTo(BigDecimal.ZERO) > 0) {
                weightedGiNumerator = weightedGiNumerator.add(ingNetCarb.multiply(ing.getGiValue()));
                totalNetCarbFromIngredients = totalNetCarbFromIngredients.add(ingNetCarb);
            }

            if (ing.getAllergenTags() != null) {
                autoTags.addAll(ing.getAllergenTags());
            }
        }

        BigDecimal netCarb = totalCarb.subtract(totalFiber).max(BigDecimal.ZERO).setScale(2, RoundingMode.HALF_UP);

        BigDecimal estimatedGi = BigDecimal.ZERO;
        if (totalNetCarbFromIngredients.compareTo(BigDecimal.ZERO) > 0) {
            estimatedGi = weightedGiNumerator.divide(totalNetCarbFromIngredients, 2, RoundingMode.HALF_UP);
        }
        BigDecimal glycemicLoad = estimatedGi.multiply(netCarb)
                .divide(new BigDecimal("100.0"), 2, RoundingMode.HALF_UP);

        dish.setPrimaryIngredientGroup(dominantGroup);
        dish.setStandardServingCookedG(totalCookedWeight.setScale(2, RoundingMode.HALF_UP));
        dish.setCaloriesKcal(totalCalories.setScale(2, RoundingMode.HALF_UP));
        dish.setTotalCarbG(totalCarb.setScale(2, RoundingMode.HALF_UP));
        dish.setFiberG(totalFiber.setScale(2, RoundingMode.HALF_UP));
        dish.setNetCarbG(netCarb);
        dish.setProteinG(totalProtein.setScale(2, RoundingMode.HALF_UP));
        dish.setFatG(totalFat.setScale(2, RoundingMode.HALF_UP));
        dish.setSaturatedFatG(totalSatFat.setScale(2, RoundingMode.HALF_UP));
        dish.setSodiumMg(totalSodium.setScale(2, RoundingMode.HALF_UP));
        dish.setPotassiumMg(totalPotassium.setScale(2, RoundingMode.HALF_UP));
        dish.setPurineMg(totalPurine.setScale(2, RoundingMode.HALF_UP));
        dish.setEstimatedGi(estimatedGi);
        dish.setGiLevel(GiLevel.fromValue(estimatedGi));
        dish.setGlycemicLoad(glycemicLoad);

        if (!Boolean.TRUE.equals(dish.getLockManualTags())) {
            if (estimatedGi.compareTo(new BigDecimal("70.0")) >= 0) autoTags.add(MedicalTag.HIGH_GI);
            if (glycemicLoad.compareTo(new BigDecimal("20.0")) >= 0) autoTags.add(MedicalTag.HIGH_GL);
            if (totalSodium.compareTo(new BigDecimal("600.0")) > 0) autoTags.add(MedicalTag.HIGH_SODIUM);
            if (totalSatFat.compareTo(new BigDecimal("5.0")) > 0 || dish.getCookingMethod() == CookingMethod.PAN_FRIED) {
                autoTags.add(MedicalTag.HIGH_SATURATED_FAT);
            }
            if (totalPurine.compareTo(new BigDecimal("150.0")) > 0) autoTags.add(MedicalTag.HIGH_PURINE);
            if (totalPotassium.compareTo(new BigDecimal("400.0")) > 0) autoTags.add(MedicalTag.HIGH_POTASSIUM);
            if (!hasAnimalProduct) autoTags.add(MedicalTag.VEGETARIAN);
            dish.setMedicalTags(autoTags);
        }

        dish.syncScaledValuesForCpSat();
    }
}
