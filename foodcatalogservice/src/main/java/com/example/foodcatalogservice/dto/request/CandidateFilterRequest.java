package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.MealSlot;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import lombok.*;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.EnumSet;
import java.util.Set;
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CandidateFilterRequest {
    private Long userId;
    @Builder.Default
    @DecimalMax("100.0")
    private BigDecimal maxGiAllowed = new BigDecimal("69.9");
    @Builder.Default
    private Set<MedicalTag> excludedMedicalTags = Set.of(MedicalTag.HIGH_GI);
    @Builder.Default
    private Set<Long> excludedRecentDishIds = Collections.emptySet();
    @Builder.Default
    private Set<Long> likedDishIds = Collections.emptySet();
    @Builder.Default
    private Set<MealSlot> requiredMealSlots = EnumSet.allOf(MealSlot.class);
    @Builder.Default
    private Integer maxCandidatesPerRole = 25;
}
