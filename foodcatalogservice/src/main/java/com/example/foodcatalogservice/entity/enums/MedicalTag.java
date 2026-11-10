package com.example.foodcatalogservice.entity.enums;

public enum MedicalTag {
    HIGH_GI,              // GI >= 70
    HIGH_GL,              // GL >= 20 trên 1 khẩu phần chuẩn
    HIGH_SODIUM,          // Sodium > 600mg (Cảnh báo Tăng huyết áp)
    HIGH_SATURATED_FAT,   // Saturated Fat > 5g (Cảnh báo Rối loạn mỡ máu)
    HIGH_PURINE,          // Purine > 150mg (Cảnh báo Gout / Tăng acid uric)
    HIGH_POTASSIUM,       // Potassium > 400mg (Cảnh báo Suy thận mạn - CKD)
    ALLERGEN_SEAFOOD,
    ALLERGEN_PEANUT,
    ALLERGEN_EGG,
    ALLERGEN_DAIRY,
    ALLERGEN_SOY,
    VEGETARIAN
}
