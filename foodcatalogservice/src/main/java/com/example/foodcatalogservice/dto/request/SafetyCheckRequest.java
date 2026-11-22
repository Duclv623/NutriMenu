package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import lombok.*;

import java.math.BigDecimal;
import java.util.Set;
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SafetyCheckRequest {
    private Set<MedicalTag> patientContraindications;
    private BigDecimal maxAllowedGlPerMeal;
}
