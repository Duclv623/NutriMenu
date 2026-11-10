package com.example.foodcatalogservice.dto.request;
import com.example.foodcatalogservice.entity.enums.MedicalTag;
import lombok.*;
import jakarta.validation.constraints.*;

import java.util.Set;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class OverrideMedicalTagsRequest {
    @NotNull private Set<MedicalTag> medicalTags;
    @NotNull private Boolean lockManualTags;
}
