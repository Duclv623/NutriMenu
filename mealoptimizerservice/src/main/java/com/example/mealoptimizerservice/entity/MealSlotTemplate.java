package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: MealSlotTemplate.java ---
@Entity
@Table(name = "meal_slot_templates", uniqueConstraints = {
        @UniqueConstraint(name = "uk_template_slot", columnNames = {"template_code", "meal_slot"})
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MealSlotTemplate {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "template_code", nullable = false, length = 50)
    private String templateCode; // VD: STANDARD_4_MEALS

    @Enumerated(EnumType.STRING)
    @Column(name = "meal_slot", nullable = false, length = 30)
    private MealSlot mealSlot;

    @Column(name = "calorie_ratio_pct", nullable = false, precision = 5, scale = 2)
    private BigDecimal calorieRatioPct; // Mặc định: Sáng 30%, Trưa 30%, Phụ 10%, Tối 30%

    @Column(name = "min_net_carb_g", nullable = false, precision = 5, scale = 2)
    private BigDecimal minNetCarbG;

    @Column(name = "max_net_carb_g", nullable = false, precision = 5, scale = 2)
    private BigDecimal maxNetCarbG;

    @Column(name = "max_gl", nullable = false, precision = 5, scale = 2)
    private BigDecimal maxGl;

    @Builder.Default
    @Column(name = "allow_composite_dish", nullable = false)
    private Boolean allowCompositeDish = false;

    @Builder.Default
    @Column(name = "req_main_starch", nullable = false)
    private Integer reqMainStarch = 0;

    @Builder.Default
    @Column(name = "req_protein_dish", nullable = false)
    private Integer reqProteinDish = 0;

    @Builder.Default
    @Column(name = "req_veggie_dish", nullable = false)
    private Integer reqVeggieDish = 0;

    @Builder.Default
    @Column(name = "req_soup", nullable = false)
    private Integer reqSoup = 0;

    @Builder.Default
    @Column(name = "req_snack", nullable = false)
    private Integer reqSnack = 0;
}
