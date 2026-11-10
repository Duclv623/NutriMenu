package com.example.foodcatalogservice.dto.request;
import lombok.*;
import jakarta.validation.constraints.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class UpdateDishStatusRequest {
    @NotNull private Boolean isActive;
}
