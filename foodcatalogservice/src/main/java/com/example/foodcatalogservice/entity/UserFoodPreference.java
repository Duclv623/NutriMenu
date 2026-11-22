package com.example.foodcatalogservice.entity;

import com.example.foodcatalogservice.entity.enums.PreferenceType;
import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "user_food_preferences", uniqueConstraints = {
        @UniqueConstraint(name = "uk_user_dish_pref", columnNames = {"user_id", "dish_id"})
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserFoodPreference {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "dish_id", nullable = false)
    private Dish dish;

    @Enumerated(EnumType.STRING)
    @Column(name = "preference_type", nullable = false, length = 20)
    private PreferenceType preferenceType;

    @Builder.Default
    @Column(name = "updated_at")
    private LocalDateTime updatedAt = LocalDateTime.now();
}
