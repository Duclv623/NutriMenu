package com.example.foodcatalogservice.repository;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.CookingMethod;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface YieldFactorRepository extends JpaRepository<YieldRetentionFactor, Long> {
    Optional<YieldRetentionFactor> findByIngredientIdAndCookingMethod(Long ingredientId, CookingMethod method);
    Optional<YieldRetentionFactor> findByIngredientGroupAndCookingMethodAndIngredientIdIsNull(
            IngredientGroup group, CookingMethod method);
}
