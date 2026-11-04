package com.menufood.userservice.dto.request;

import com.menufood.userservice.entity.ActivityLevel;
import com.menufood.userservice.entity.Gender;
import com.menufood.userservice.entity.WeightGoal;
import jakarta.validation.constraints.*;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.Period;
import java.util.LinkedHashSet;
import java.util.Set;

@Getter
@Setter
public class UserProfileRequestDTO {
    @NotNull(message = "Ngày sinh không được để trống")
    @Past(message = "Ngày sinh phải nằm trong quá khứ")
    private LocalDate dateOfBirth;

    @NotNull(message = "Giới tính không được để trống")
    private Gender gender;

    @NotNull(message = "Chiều cao không được để trống")
    @DecimalMin(value = "0", inclusive = false, message = "Chiều cao phải lớn hơn 0 cm")
    @Digits(integer = 3, fraction = 2, message = "Chiều cao tối đa 3 chữ số nguyên và 2 chữ số thập phân")
    private BigDecimal height;

    @NotNull(message = "Cân nặng không được để trống")
    @DecimalMin(value = "0", inclusive = false, message = "Cân nặng phải lớn hơn 0 kg")
    @Digits(integer = 3, fraction = 2, message = "Cân nặng tối đa 3 chữ số nguyên và 2 chữ số thập phân")
    private BigDecimal weight;

    @NotNull(message = "Mức vận động không được để trống")
    private ActivityLevel activityLevel;

    @NotNull(message = "Mục tiêu không được để trống")
    private WeightGoal goal;

    @DecimalMin(value = "0", inclusive = false, message = "Cân nặng mục tiêu phải lớn hơn 0 kg")
    @Digits(integer = 3, fraction = 2, message = "Cân nặng mục tiêu tối đa 3 chữ số nguyên và 2 chữ số thập phân")
    private BigDecimal targetWeight;

    @NotNull
    @Size(max = 100)
    private Set<@NotBlank @Size(max = 100) String> allergies = new LinkedHashSet<>();

    @NotNull
    @Size(max = 100)
    private Set<@NotBlank @Size(max = 100) String> restrictedIngredients = new LinkedHashSet<>();

    @NotNull
    @Size(max = 100)
    private Set<@NotBlank @Size(max = 100) String> preferences = new LinkedHashSet<>();

    @AssertTrue(message = "Hệ thống hiện chỉ hỗ trợ người từ đủ 18 tuổi")
    public boolean isAdult() {
        return dateOfBirth == null || Period.between(dateOfBirth, LocalDate.now()).getYears() >= 18;
    }
}
