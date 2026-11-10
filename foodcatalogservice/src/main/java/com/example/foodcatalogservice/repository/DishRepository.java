package com.example.foodcatalogservice.repository;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.DishRole;
import com.example.foodcatalogservice.entity.enums.GiLevel;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
@Repository
public interface DishRepository extends JpaRepository<Dish, Long> {

    @Query("""
        SELECT DISTINCT d FROM Dish d
        JOIN d.mealSlots ms
        WHERE d.isActive = true
          AND (d.createdByUserId IS NULL OR d.createdByUserId = :userId)
          AND d.estimatedGi <= :maxGi
          AND ms IN :slots
          AND (:hasExcludedIds = false OR d.id NOT IN :excludedDishIds)
          AND NOT EXISTS (
              SELECT 1 FROM Dish d2 JOIN d2.medicalTags mt
              WHERE d2 = d AND mt IN :excludedTags
          )
        ORDER BY d.popularityScore DESC, d.glycemicLoad ASC
    """)
    List<Dish> findCandidatesForSolver(
            @Param("userId") Long userId,
            @Param("maxGi") BigDecimal maxGi,
            @Param("slots") Set<MealSlot> slots,
            @Param("hasExcludedIds") boolean hasExcludedIds,
            @Param("excludedDishIds") Set<Long> excludedDishIds,
            @Param("excludedTags") Set<MedicalTag> excludedTags
    );

    @Query("""
        SELECT DISTINCT d FROM Dish d
        LEFT JOIN d.mealSlots ms
        WHERE d.isActive = true
          AND (d.createdByUserId IS NULL OR d.createdByUserId = :userId)
          AND (:role IS NULL OR d.dishRole = :role)
          AND (:slot IS NULL OR ms = :slot)
          AND (:giLevel IS NULL OR d.giLevel = :giLevel)
          AND (:kw IS NULL OR :kw = '' OR d.nameNormalized LIKE CONCAT('%', :kw, '%'))
        ORDER BY d.glycemicLoad ASC, d.popularityScore DESC
    """)
    Page<Dish> searchDishesForUser(
            @Param("userId") Long userId,
            @Param("role") DishRole role,
            @Param("slot") MealSlot slot,
            @Param("giLevel") GiLevel giLevel,
            @Param("kw") String normalizedKeyword,
            Pageable pageable
    );

    @Query("""
        SELECT DISTINCT d FROM Dish d
        JOIN d.mealSlots ms
        WHERE d.isActive = true
          AND d.id <> :currentDishId
          AND d.dishRole = :role
          AND (:slot IS NULL OR ms = :slot)
          AND d.giLevel IN ('NONE', 'LOW', 'MEDIUM')
          AND d.netCarbG BETWEEN :minCarb AND :maxCarb
          AND d.caloriesKcal BETWEEN :minCal AND :maxCal
        ORDER BY ABS(d.glycemicLoad - :targetGl) ASC
    """)
    List<Dish> findSimilarAlternatives(
            @Param("currentDishId") Long currentDishId,
            @Param("role") DishRole role,
            @Param("slot") MealSlot slot,
            @Param("minCarb") BigDecimal minCarb,
            @Param("maxCarb") BigDecimal maxCarb,
            @Param("minCal") BigDecimal minCal,
            @Param("maxCal") BigDecimal maxCal,
            @Param("targetGl") BigDecimal targetGl
    );
}
