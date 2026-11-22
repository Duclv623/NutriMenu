package com.example.foodcatalogservice.dto.response;
import lombok.*;
import jakarta.validation.constraints.*;

import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class BulkImportReportResponse {
    private int totalProcessed;
    private int insertedCount;
    private int updatedCount;
    private List<String> errors;
}
