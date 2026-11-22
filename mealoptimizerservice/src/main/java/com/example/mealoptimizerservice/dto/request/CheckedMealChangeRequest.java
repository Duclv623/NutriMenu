package com.example.mealoptimizerservice.dto.request;

import com.example.mealoptimizerservice.entity.enums.MedicalTag;
import jakarta.validation.constraints.*;
import lombok.*;
import java.util.*;

@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class CheckedMealChangeRequest {
    @NotNull @PositiveOrZero private Long expectedVersion;
    @NotNull @Positive private Long itemId;
    @NotNull @Positive private Long newDishId;
    @NotNull @Min(1) @Max(6) private Integer newServingScaledX2;
    @NotNull @Builder.Default private Set<@Positive Long> excludedDishIds = new HashSet<>();
    @NotNull @Builder.Default private Set<MedicalTag> contraindications = new HashSet<>();
    @Size(max=100) private String previewSignature;
}
