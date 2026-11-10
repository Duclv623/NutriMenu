package com.example.foodcatalogservice.dto.request;

import com.example.foodcatalogservice.entity.enums.IngredientGroup;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import jakarta.validation.constraints.*;
import lombok.*;

import java.math.BigDecimal;
import java.util.*;

// --- DTOs cho Admin ---
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UpsertIngredientRequest {
    @NotBlank private String vfcCode;
    @NotBlank private String nameVi;
    @NotNull private IngredientGroup ingredientGroup;
    private BigDecimal ediblePortionPct;
    @NotNull @DecimalMin("0.0") private BigDecimal caloriesPer100g;
    @NotNull @DecimalMin("0.0") private BigDecimal totalCarbG;
    @NotNull @DecimalMin("0.0") private BigDecimal fiberG;
    @NotNull @DecimalMin("0.0") private BigDecimal proteinG;
    @NotNull @DecimalMin("0.0") private BigDecimal fatG;
    private BigDecimal saturatedFatG;
    private BigDecimal sodiumMg;
    private BigDecimal potassiumMg;
    private BigDecimal purineMg;
    @NotNull @DecimalMin("0.0") @DecimalMax("100.0") private BigDecimal giValue;
    private Set<MedicalTag> allergenTags;
}
