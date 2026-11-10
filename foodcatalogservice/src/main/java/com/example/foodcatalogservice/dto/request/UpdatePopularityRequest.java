package com.example.foodcatalogservice.dto.request;
import lombok.*;
import jakarta.validation.constraints.*;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class UpdatePopularityRequest {
    @NotNull @Min(1) @Max(1000) private Integer popularityScore;
}
