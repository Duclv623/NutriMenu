package com.example.foodcatalogservice.config;

import com.example.foodcatalogservice.dto.request.CreateDishRequest;
import com.example.foodcatalogservice.dto.request.OverrideMedicalTagsRequest;
import com.example.foodcatalogservice.dto.request.RecipeItemRequest;
import com.example.foodcatalogservice.dto.request.UpsertIngredientRequest;
import com.example.foodcatalogservice.dto.request.UpsertYieldFactorRequest;
import com.example.foodcatalogservice.entity.Dish;
import com.example.foodcatalogservice.entity.Ingredient;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import com.example.foodcatalogservice.entity.enums.PreferenceType;
import com.example.foodcatalogservice.repository.DishRepository;
import com.example.foodcatalogservice.repository.IngredientRepository;
import com.example.foodcatalogservice.repository.UserFoodPreferenceRepository;
import com.example.foodcatalogservice.repository.YieldFactorRepository;
import com.example.foodcatalogservice.service.FoodCatalogService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Slf4j
@Configuration(proxyBeanMethods = false)
@RequiredArgsConstructor
@ConditionalOnProperty(prefix = "app.catalog", name = "seed-enabled", havingValue = "true", matchIfMissing = true)
public class CatalogDataSeederConfig {

    private static final String SEED_RESOURCE = "catalog/food-catalog-vi-qa.json";

    private final ObjectMapper objectMapper;
    private final PlatformTransactionManager transactionManager;
    private final JdbcTemplate jdbcTemplate;
    private final IngredientRepository ingredientRepository;
    private final YieldFactorRepository yieldFactorRepository;
    private final DishRepository dishRepository;
    private final UserFoodPreferenceRepository preferenceRepository;
    private final FoodCatalogService catalogService;

    @Bean
    public CommandLineRunner seedVietnameseDiabeticCatalog() {
        return args -> {
            CatalogSeed data;
            try (var stream = new ClassPathResource(SEED_RESOURCE).getInputStream()) {
                data = objectMapper.readValue(stream, CatalogSeed.class);
            }
            if (data.metadata().schemaVersion() != 1) {
                throw new IllegalStateException("Unsupported Food Catalog seed schema: " + data.metadata().schemaVersion());
            }

            new TransactionTemplate(transactionManager).executeWithoutResult(status -> seed(data));
            log.info("Catalog dataset {} ready: {} ingredient codes, {} yield rules, {} dish codes, {} preferences",
                    data.metadata().datasetId(), data.ingredients().size(), data.yieldRetentionFactors().size(),
                    data.dishes().size(), data.userFoodPreferences().size());
        };
    }

    private void seed(CatalogSeed data) {
        // Serialize startup imports using the catalog database transaction.
        jdbcTemplate.execute("SELECT pg_advisory_xact_lock(8132, 1)");

        Map<String, Long> ingredientIds = new HashMap<>();
        for (UpsertIngredientRequest ingredient : data.ingredients()) {
            Long id = ingredientRepository.findByVfcCode(ingredient.getVfcCode())
                    .map(Ingredient::getId)
                    .orElseGet(() -> catalogService.createIngredient(ingredient).getId());
            ingredientIds.put(ingredient.getVfcCode(), id);
        }
        for (YieldSeed factor : data.yieldRetentionFactors()) {
            seedYieldFactor(factor, ingredientIds);
        }

        Map<String, Long> dishIds = new HashMap<>();
        for (DishSeed dish : data.dishes()) {
            Long id = dishRepository.findByCode(dish.code())
                    .map(Dish::getId)
                    .orElseGet(() -> createDish(dish, ingredientIds));
            dishIds.put(dish.code(), id);
        }
        for (PreferenceSeed preference : data.userFoodPreferences()) {
            Long dishId = requiredId(dishIds, preference.dishCode(), "dish");
            if (preferenceRepository.findByUserIdAndDishId(preference.userId(), dishId).isEmpty()) {
                catalogService.setUserDishPreference(preference.userId(), dishId, preference.preferenceType());
            }
        }
    }

    private void seedYieldFactor(YieldSeed factor, Map<String, Long> ingredientIds) {
        Long ingredientId = factor.ingredientCode() == null
                ? null : requiredId(ingredientIds, factor.ingredientCode(), "ingredient");
        boolean exists = ingredientId == null
                ? yieldFactorRepository.findByIngredientGroupAndCookingMethodAndIngredientIdIsNull(
                        factor.ingredientGroup(), factor.cookingMethod()).isPresent()
                : yieldFactorRepository.findByIngredientIdAndCookingMethod(ingredientId, factor.cookingMethod()).isPresent();
        if (!exists) {
            catalogService.upsertYieldFactor(UpsertYieldFactorRequest.builder()
                    .ingredientId(ingredientId)
                    .ingredientGroup(factor.ingredientGroup())
                    .cookingMethod(factor.cookingMethod())
                    .yieldFactor(factor.yieldFactor())
                    .oilAbsorptionPct(factor.oilAbsorptionPct())
                    .build());
        }
    }

    private Long createDish(DishSeed dish, Map<String, Long> ingredientIds) {
        List<RecipeItemRequest> recipe = dish.recipeItems().stream()
                .map(item -> RecipeItemRequest.builder()
                        .ingredientId(requiredId(ingredientIds, item.ingredientCode(), "ingredient"))
                        .rawWeightG(item.rawWeightG())
                        .isMainIngredient(item.mainIngredient())
                        .build())
                .toList();

        Long id = catalogService.createDish(CreateDishRequest.builder()
                .code(dish.code())
                .nameVi(dish.nameVi())
                .cookingMethod(dish.cookingMethod())
                .dishRole(dish.dishRole())
                .mealSlots(dish.mealSlots())
                .householdUnitLabel(dish.householdUnitLabel())
                .minServingScaledX2(dish.minServingScaledX2())
                .maxServingScaledX2(dish.maxServingScaledX2())
                .stepServingScaledX2(dish.stepServingScaledX2())
                .recipeItems(recipe)
                .build(), dish.createdByUserId()).getId();

        catalogService.updateDishPopularity(id, dish.popularityScore());
        if (!dish.isActive()) {
            catalogService.updateDishStatus(id, false);
        }
        if (Boolean.TRUE.equals(dish.lockManualTags())) {
            catalogService.overrideMedicalTags(id, new OverrideMedicalTagsRequest(dish.manualMedicalTags(), true));
        }
        return id;
    }

    private static Long requiredId(Map<String, Long> ids, String code, String entity) {
        Long id = ids.get(code);
        if (id == null) {
            throw new IllegalArgumentException("Unknown seed " + entity + " code: " + code);
        }
        return id;
    }

    private record CatalogSeed(SeedMetadata metadata, List<UpsertIngredientRequest> ingredients,
                               List<YieldSeed> yieldRetentionFactors, List<DishSeed> dishes,
                               List<PreferenceSeed> userFoodPreferences) {
    }

    private record SeedMetadata(String datasetId, int schemaVersion, List<Source> sources) {
    }

    private record Source(String key, String description, String url) {
    }

    private record YieldSeed(String ingredientCode, IngredientGroup ingredientGroup, CookingMethod cookingMethod,
                             BigDecimal yieldFactor, BigDecimal oilAbsorptionPct) {
    }

    private record DishSeed(String code, String nameVi, CookingMethod cookingMethod, DishRole dishRole,
                            Set<MealSlot> mealSlots, String householdUnitLabel, Integer minServingScaledX2,
                            Integer maxServingScaledX2, Integer stepServingScaledX2, boolean isActive,
                            Long createdByUserId, int popularityScore, List<RecipeSeed> recipeItems,
                            Set<MedicalTag> manualMedicalTags, Boolean lockManualTags) {
    }

    private record RecipeSeed(String ingredientCode, BigDecimal rawWeightG, boolean mainIngredient) {
    }

    private record PreferenceSeed(Long userId, String dishCode, PreferenceType preferenceType) {
    }
}
