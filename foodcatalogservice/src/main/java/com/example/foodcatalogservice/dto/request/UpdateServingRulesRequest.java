package com.example.foodcatalogservice.dto.request;
import lombok.*;
import jakarta.validation.constraints.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UpdateServingRulesRequest {
    @NotNull @Min(1) @Max(6) private Integer minServingScaledX2;
    @NotNull @Min(1) @Max(8) private Integer maxServingScaledX2;
    @NotNull @Min(1) @Max(2) private Integer stepServingScaledX2;
    @NotBlank private String householdUnitLabel;
}
