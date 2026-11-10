package com.example.foodcatalogservice.dto.response;
import lombok.*;
import jakarta.validation.constraints.*;

import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CascadeRecalculationResponse {
    private Long ingredientId;
    private String ingredientName;
    private int affectedDishesCount;
    private List<String> updatedDishCodes;
}
