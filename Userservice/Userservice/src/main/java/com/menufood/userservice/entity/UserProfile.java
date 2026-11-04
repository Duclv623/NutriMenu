package com.menufood.userservice.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

@Entity
@Table(name = "user_profiles")
@Getter
@Setter
@NoArgsConstructor
public class UserProfile {
    @Id
    @Column(name = "user_id")
    private UUID userId;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "user_id")
    private User user;

    @Column(name = "date_of_birth", nullable = false)
    private LocalDate dateOfBirth;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Gender gender;

    @Column(nullable = false, precision = 5, scale = 2)
    private BigDecimal height;

    @Column(nullable = false, precision = 5, scale = 2)
    private BigDecimal weight;

    @Enumerated(EnumType.STRING)
    @Column(name = "activity_level", nullable = false, length = 20)
    private ActivityLevel activityLevel;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WeightGoal goal;

    @Column(name = "target_weight", precision = 5, scale = 2)
    private BigDecimal targetWeight;

    @ElementCollection
    @CollectionTable(name = "user_allergies", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "ingredient", nullable = false, length = 100)
    private Set<String> allergies = new LinkedHashSet<>();

    @ElementCollection
    @CollectionTable(name = "user_restricted_ingredients", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "ingredient", nullable = false, length = 100)
    private Set<String> restrictedIngredients = new LinkedHashSet<>();

    @ElementCollection
    @CollectionTable(name = "user_preferences", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "preference", nullable = false, length = 100)
    private Set<String> preferences = new LinkedHashSet<>();

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }
}
