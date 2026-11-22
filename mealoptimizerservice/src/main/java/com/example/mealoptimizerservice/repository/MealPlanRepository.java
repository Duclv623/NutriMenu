package com.example.mealoptimizerservice.repository;

import com.example.mealoptimizerservice.entity.*;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.Set;

@Repository
public interface MealPlanRepository extends JpaRepository<MealPlan, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT mp FROM MealPlan mp WHERE mp.id = :id AND mp.userId = :userId")
    Optional<MealPlan> findOwnedForUpdate(@Param("id") Long id, @Param("userId") Long userId);
    Page<MealPlan> findByUserIdOrderByPlanDateDesc(Long userId, Pageable pageable);
    Optional<MealPlan> findByUserIdAndPlanDate(Long userId, LocalDate planDate);
    List<MealPlan> findByUserIdAndPlanDateBetweenOrderByPlanDateAsc(Long userId, LocalDate from, LocalDate to);

    @Query("""
        SELECT DISTINCT mpi.dishId FROM MealPlan mp
        JOIN mp.items mpi
        WHERE mp.userId = :userId
          AND mp.planDate >= :sinceDate
          AND mp.planDate < :beforeDate
          AND mpi.catalogDish = true
          AND mpi.status <> 'SKIPPED'
    """)
    Set<Long> findRecentDishIdsByUserId(@Param("userId") Long userId,
                                       @Param("sinceDate") LocalDate sinceDate,
                                       @Param("beforeDate") LocalDate beforeDate);
}
