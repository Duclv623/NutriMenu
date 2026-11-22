package com.example.foodcatalogservice.repository;
import com.example.foodcatalogservice.entity.*;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface DishIngredientRepository extends JpaRepository<DishIngredient, Long> {
    boolean existsByIngredientId(Long ingredientId);

    @Query("SELECT DISTINCT di.dish.id FROM DishIngredient di WHERE di.ingredient.id = :ingredientId")
    List<Long> findDishIdsByIngredientId(@Param("ingredientId") Long ingredientId);
}
