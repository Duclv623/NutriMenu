package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import lombok.*;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.util.Set;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SolverCoverageDiagnosticRequest {
    @DecimalMax("100.0") private BigDecimal maxGiAllowed;
    private Set<MedicalTag> excludedMedicalTags;
    private Set<Long> excludedRecentDishIds;
}
