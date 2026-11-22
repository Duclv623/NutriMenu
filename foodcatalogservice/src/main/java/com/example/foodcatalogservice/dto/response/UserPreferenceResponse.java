package com.example.foodcatalogservice.dto.response;
import lombok.*;

import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserPreferenceResponse {
    private Long userId;
    private List<DishDetailResponse> favoriteDishes;
    private List<DishDetailResponse> dislikedDishes;
}
