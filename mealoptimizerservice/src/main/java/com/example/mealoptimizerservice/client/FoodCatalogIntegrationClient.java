package com.example.mealoptimizerservice.client;

import com.example.mealoptimizerservice.dto.DishSolverDto;
import com.example.mealoptimizerservice.entity.enums.MealSlot;
import com.example.mealoptimizerservice.entity.enums.MedicalTag;
import com.example.mealoptimizerservice.exception.OptimizerBusinessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.Set;

@Slf4j
@Component
public class FoodCatalogIntegrationClient {

    private static final String DISHES_PATH = "/api/v1/internal/dishes";

    private final RestClient restClient;

    public FoodCatalogIntegrationClient(@Value("${app.services.food-catalog-url}") String foodCatalogUrl) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(2_000);
        requestFactory.setReadTimeout(3_000);
        this.restClient = RestClient.builder()
                .baseUrl(foodCatalogUrl)
                .requestFactory(requestFactory)
                .build();
    }

    public List<DishSolverDto> fetchCandidatesForSolver(
            Long userId, BigDecimal maxGi, Set<MedicalTag> contraindications,
            Set<Long> excludedDishIds, Set<MealSlot> requiredMealSlots) {
        try {
            List<DishSolverDto> dishes = restClient.post()
                    .uri(DISHES_PATH + "/candidates")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new CandidateFilter(userId, maxGi, contraindications, excludedDishIds, requiredMealSlots))
                    .retrieve()
                    .body(new ParameterizedTypeReference<List<DishSolverDto>>() {});
            if (dishes == null) {
                throw new OptimizerBusinessException(HttpStatus.BAD_GATEWAY, "Food Catalog không trả về danh sách món ăn.");
            }
            return dishes;
        } catch (RestClientException e) {
            throw catalogFailure(e);
        }
    }

    public Optional<DishSolverDto> findDishById(Long dishId, Long userId, boolean activeOnly) {
        try {
            DishSolverDto dish = restClient.get()
                    .uri(builder -> builder.path(DISHES_PATH + "/{id}/solver-dto")
                            .queryParamIfPresent("userId", Optional.ofNullable(userId))
                            .queryParam("activeOnly", activeOnly)
                            .build(dishId))
                    .retrieve()
                    .body(DishSolverDto.class);
            if (dish == null) {
                throw new OptimizerBusinessException(HttpStatus.BAD_GATEWAY, "Food Catalog không trả về thông tin món ăn.");
            }
            return Optional.of(dish);
        } catch (HttpClientErrorException.NotFound e) {
            return Optional.empty();
        } catch (RestClientException e) {
            throw catalogFailure(e);
        }
    }

    private OptimizerBusinessException catalogFailure(RestClientException error) {
        log.warn("Food Catalog request failed ({})", error.getClass().getSimpleName());
        if (error instanceof ResourceAccessException) {
            return new OptimizerBusinessException(HttpStatus.SERVICE_UNAVAILABLE, "Không kết nối được với Food Catalog.");
        }
        return new OptimizerBusinessException(HttpStatus.BAD_GATEWAY, "Food Catalog trả về lỗi khi lấy dữ liệu món ăn.");
    }

    private record CandidateFilter(
            Long userId,
            BigDecimal maxGiAllowed,
            Set<MedicalTag> excludedMedicalTags,
            Set<Long> excludedRecentDishIds,
            Set<MealSlot> requiredMealSlots) {
    }
}
