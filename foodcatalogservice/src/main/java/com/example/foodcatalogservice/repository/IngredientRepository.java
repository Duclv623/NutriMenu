package com.example.foodcatalogservice.repository;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.GiLevel;
import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface IngredientRepository extends JpaRepository<Ingredient, Long> {
    Optional<Ingredient> findByVfcCode(String vfcCode);

    @Query("""
        SELECT i FROM Ingredient i
        WHERE (:group IS NULL OR i.ingredientGroup = :group)
          AND (:giLevel IS NULL OR i.giLevel = :giLevel)
          AND (:kw IS NULL OR :kw = '' OR i.nameNormalized LIKE CONCAT('%', :kw, '%') OR LOWER(i.vfcCode) LIKE CONCAT('%', :kw, '%'))
        ORDER BY i.nameVi ASC
    """)
    Page<Ingredient> searchIngredients(
            @Param("group") IngredientGroup group,
            @Param("giLevel") GiLevel giLevel,
            @Param("kw") String normalizedKeyword,
            Pageable pageable
    );
}
