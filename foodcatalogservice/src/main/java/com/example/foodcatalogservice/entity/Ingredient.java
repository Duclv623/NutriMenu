package com.example.foodcatalogservice.entity;

import com.example.foodcatalogservice.entity.enums.GiLevel;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import com.example.foodcatalogservice.service.VietnameseTextUtils;
import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "ingredients", indexes = {
        @Index(name = "idx_ing_group", columnList = "ingredient_group"),
        @Index(name = "idx_ing_gi", columnList = "gi_level, gi_value")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Ingredient {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "vfc_code", unique = true, length = 30)
    private String vfcCode;

    @Column(name = "name_vi", nullable = false, length = 150)
    private String nameVi;

    @Column(name = "name_normalized", nullable = false, length = 150)
    private String nameNormalized;

    @Enumerated(EnumType.STRING)
    @Column(name = "ingredient_group", nullable = false, length = 30)
    private IngredientGroup ingredientGroup;

    @Builder.Default
    @Column(name = "edible_portion_pct", precision = 5, scale = 2)
    private BigDecimal ediblePortionPct = new BigDecimal("100.00");

    @Builder.Default
    @Column(name = "calories_per_100g", nullable = false, precision = 7, scale = 2)
    private BigDecimal caloriesPer100g = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "total_carb_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal totalCarbG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "fiber_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal fiberG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "protein_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal proteinG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "fat_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal fatG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "saturated_fat_g", precision = 6, scale = 2)
    private BigDecimal saturatedFatG = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "sodium_mg", precision = 7, scale = 2)
    private BigDecimal sodiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "potassium_mg", precision = 7, scale = 2)
    private BigDecimal potassiumMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "purine_mg", precision = 7, scale = 2)
    private BigDecimal purineMg = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "gi_value", precision = 5, scale = 2)
    private BigDecimal giValue = BigDecimal.ZERO;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "gi_level", nullable = false, length = 15)
    private GiLevel giLevel = GiLevel.LOW;

    @Builder.Default
    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "ingredient_allergens", joinColumns = @JoinColumn(name = "ingredient_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "allergen_tag", length = 30)
    private Set<MedicalTag> allergenTags = new HashSet<>();

    @PrePersist
    @PreUpdate
    public void normalizeFields() {
        this.nameNormalized = VietnameseTextUtils.removeAccents(this.nameVi);
        this.giLevel = GiLevel.fromValue(this.giValue);
    }

    public BigDecimal getNetCarbPer100g() {
        return totalCarbG.subtract(fiberG).max(BigDecimal.ZERO);
    }
}
