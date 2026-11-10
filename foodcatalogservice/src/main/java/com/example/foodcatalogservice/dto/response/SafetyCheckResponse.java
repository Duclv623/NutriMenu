package com.example.foodcatalogservice.dto.response;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import com.example.foodcatalogservice.entity.enums.TrafficLightBadge;
import lombok.*;

import java.util.List;
import java.util.Set;
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SafetyCheckResponse {
    private Long dishId;
    private String dishNameVi;
    private boolean isSafeForPatient;
    private TrafficLightBadge badge;
    private Set<MedicalTag> conflictingTags;
    private List<String> detailedWarnings;
    private List<String> cookingAdjustmentTips;
}
