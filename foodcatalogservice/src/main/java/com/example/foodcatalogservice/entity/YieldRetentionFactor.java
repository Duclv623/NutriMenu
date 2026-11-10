package com.example.foodcatalogservice.entity;

import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;

@Entity
@Table(name = "yield_retention_factors", indexes = {
        @Index(name = "idx_group_cooking", columnList = "ingredient_group, cooking_method")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class YieldRetentionFactor {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "ingredient_id")
    private Long ingredientId;

    @Enumerated(EnumType.STRING)
    @Column(name = "ingredient_group", nullable = false, length = 30)
    private IngredientGroup ingredientGroup;

    @Enumerated(EnumType.STRING)
    @Column(name = "cooking_method", nullable = false, length = 30)
    private CookingMethod cookingMethod;

    @Builder.Default
    @Column(name = "yield_factor", nullable = false, precision = 5, scale = 3)
    private BigDecimal yieldFactor = BigDecimal.ONE;

    @Builder.Default
    @Column(name = "oil_absorption_pct", precision = 5, scale = 2)
    private BigDecimal oilAbsorptionPct = BigDecimal.ZERO;
}


