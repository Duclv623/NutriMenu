package com.example.foodcatalogservice.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;

@Entity
@Table(name = "dish_ingredients", uniqueConstraints = {
        @UniqueConstraint(name = "uk_dish_ingredient", columnNames = {"dish_id", "ingredient_id"})
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DishIngredient {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "dish_id", nullable = false)
    private Dish dish;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "ingredient_id", nullable = false)
    private Ingredient ingredient;

    @Column(name = "raw_weight_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal rawWeightG;

    @Column(name = "applied_yield_factor", nullable = false, precision = 5, scale = 3)
    private BigDecimal appliedYieldFactor;

    @Column(name = "cooked_weight_g", nullable = false, precision = 6, scale = 2)
    private BigDecimal cookedWeightG;

    @Builder.Default
    @Column(name = "is_main_ingredient", nullable = false)
    private Boolean isMainIngredient = false;
}
