package com.example.foodcatalogservice.dto.response;
import com.example.foodcatalogservice.entity.enums.GiLevel;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import com.example.foodcatalogservice.entity.enums.TrafficLightBadge;
import lombok.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SimulationResultResponse {
    private BigDecimal totalRawWeightG;
    private BigDecimal totalCookedWeightG;
    private BigDecimal caloriesKcal;
    private BigDecimal totalCarbG;
    private BigDecimal fiberG;
    private BigDecimal netCarbG;
    private BigDecimal proteinG;
    private BigDecimal fatG;
    private BigDecimal saturatedFatG;
    private BigDecimal sodiumMg;
    private BigDecimal potassiumMg;
    private BigDecimal purineMg;
    private BigDecimal estimatedGi;
    private GiLevel giLevel;
    private BigDecimal glycemicLoad;
    private TrafficLightBadge trafficLightBadge;
    private Set<MedicalTag> triggeredMedicalTags;
    private List<String> medicalRecommendations;
}
