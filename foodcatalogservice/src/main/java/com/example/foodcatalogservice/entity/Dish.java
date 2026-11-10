package com.example.foodcatalogservice.entity;

import com.example.foodcatalogservice.entity.enums.*;
import com.example.foodcatalogservice.service.VietnameseTextUtils;
import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;


@Entity
@Table(name = "dishes", indexes = {
        @Index(name = "idx_cpsat_prefilter", columnList = "is_active, gi_level, dish_role, estimated_gi")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Dish {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String code;

    @Column(name = "name_vi", nullable = false, length = 200)
    private String nameVi;

    @Column(name = "name_normalized", nullable = false, length = 200)
    private String nameNormalized;

    @Column(name = "image_url", length = 500)
    private String imageUrl;

    @Column(name = "diabetic_cooking_tip", length = 500)
    private String diabeticCookingTip;

    @Enumerated(EnumType.STRING)
    @Column(name = "cooking_method", nullable = false, length = 30)
    private CookingMethod cookingMethod;

    @Enumerated(EnumType.STRING)
    @Column(name = "dish_role", nullable = false, length = 30)
    private DishRole dishRole;

    @Enumerated(EnumType.STRING)
    @Column(name = "primary_ingredient_group", nullable = false, length = 30)
    private IngredientGroup primaryIngredientGroup;

    @Builder.Default
    @Column(name = "standard_serving_cooked_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal standardServingCookedG = BigDecimal.ZERO;

    @Column(name = "household_unit_label", nullable = false, length = 100)
    private String householdUnitLabel;

    @Builder.Default
    @Column(name = "calories_kcal", nullable = false, precision = 7, scale = 2)
    private BigDecimal caloriesKcal = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "total_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal totalCarbG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "fiber_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal fiberG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "net_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal netCarbG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "protein_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal proteinG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal fatG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "saturated_fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal saturatedFatG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "sodium_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal sodiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "potassium_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal potassiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "purine_mg", nullable = false, precision = 7, scale = 2)
    private BigDecimal purineMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "estimated_gi", nullable = false, precision = 5, scale = 2)
    private BigDecimal estimatedGi = BigDecimal.ZERO;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "gi_level", nullable = false, length = 15)
    private GiLevel giLevel = GiLevel.LOW;

    @Builder.Default
    @Column(name = "glycemic_load", nullable = false, precision = 5, scale = 2)
    private BigDecimal glycemicLoad = BigDecimal.ZERO;

    // Các cột số nguyên nhân 10 (Scaling x10) nạp thẳng vào OR-Tools CP-SAT
    @Builder.Default
    @Column(name = "calories_scaled_x10", nullable = false)
    private Long caloriesScaledX10 = 0L;

    @Builder.Default
    @Column(name = "net_carb_scaled_x10", nullable = false)
    private Long netCarbScaledX10 = 0L;

    @Builder.Default
    @Column(name = "fiber_scaled_x10", nullable = false)
    private Long fiberScaledX10 = 0L;

    @Builder.Default
    @Column(name = "protein_scaled_x10", nullable = false)
    private Long proteinScaledX10 = 0L;

    @Builder.Default
    @Column(name = "fat_scaled_x10", nullable = false)
    private Long fatScaledX10 = 0L;

    @Builder.Default
    @Column(name = "gl_scaled_x10", nullable = false)
    private Long glScaledX10 = 0L;

    // Quy tắc bội số khẩu phần cho CP-SAT (x2: 1=0.5, 2=1.0, 3=1.5)
    @Builder.Default
    @Column(name = "min_serving_scaled_x2", nullable = false)
    private Integer minServingScaledX2 = 2;

    @Builder.Default
    @Column(name = "max_serving_scaled_x2", nullable = false)
    private Integer maxServingScaledX2 = 2;

    @Builder.Default
    @Column(name = "step_serving_scaled_x2", nullable = false)
    private Integer stepServingScaledX2 = 2;

    @Builder.Default
    @Column(name = "is_active", nullable = false)
    private Boolean isActive = true;

    @Builder.Default
    @Column(name = "popularity_score", nullable = false)
    private Integer popularityScore = 100;

    @Builder.Default
    @Column(name = "lock_manual_tags", nullable = false)
    private Boolean lockManualTags = false;

    @Column(name = "created_by_user_id")
    private Long createdByUserId;

    @Builder.Default
    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "dish_meal_slots", joinColumns = @JoinColumn(name = "dish_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "meal_slot", length = 30)
    private Set<MealSlot> mealSlots = new HashSet<>();

    @Builder.Default
    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "dish_medical_tags", joinColumns = @JoinColumn(name = "dish_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "medical_tag", length = 30)
    private Set<MedicalTag> medicalTags = new HashSet<>();

    @Builder.Default
    @OneToMany(mappedBy = "dish", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    private List<DishIngredient> ingredients = new ArrayList<>();

    @Builder.Default
    @Column(name = "updated_at")
    private LocalDateTime updatedAt = LocalDateTime.now();

    @PrePersist
    @PreUpdate
    public void syncScaledValuesForCpSat() {
        this.nameNormalized = VietnameseTextUtils.removeAccents(this.nameVi);
        this.caloriesScaledX10 = scaleX10(this.caloriesKcal);
        this.netCarbScaledX10 = scaleX10(this.netCarbG);
        this.fiberScaledX10 = scaleX10(this.fiberG);
        this.proteinScaledX10 = scaleX10(this.proteinG);
        this.fatScaledX10 = scaleX10(this.fatG);
        this.glScaledX10 = scaleX10(this.glycemicLoad);
        this.updatedAt = LocalDateTime.now();
    }

    private static Long scaleX10(BigDecimal val) {
        if (val == null) return 0L;
        return val.multiply(BigDecimal.TEN).setScale(0, RoundingMode.HALF_UP).longValue();
    }
}
