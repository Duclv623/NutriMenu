package com.example.foodcatalogservice.repository;
import com.example.foodcatalogservice.entity.*;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface UserFoodPreferenceRepository extends JpaRepository<UserFoodPreference, Long> {
    List<UserFoodPreference> findByUserId(Long userId);
    Optional<UserFoodPreference> findByUserIdAndDishId(Long userId, Long dishId);
}
