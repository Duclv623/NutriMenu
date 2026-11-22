package com.example.foodcatalogservice.service;

import com.example.foodcatalogservice.dto.request.*;
import com.example.foodcatalogservice.dto.response.*;
import com.example.foodcatalogservice.entity.*;
import com.example.foodcatalogservice.entity.enums.*;
import com.example.foodcatalogservice.exception.BusinessRuleException;
import com.example.foodcatalogservice.exception.ResourceNotFoundException;
import com.example.foodcatalogservice.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.Normalizer;
import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class VietnameseTextUtils {
    private static final Pattern DIACRITICS = Pattern.compile("\\p{InCombiningDiacriticalMarks}+");

    public static String removeAccents(String input) {
        if (input == null || input.isBlank()) return "";
        String temp = Normalizer.normalize(input.trim().toLowerCase(Locale.ROOT), Normalizer.Form.NFD);
        return DIACRITICS.matcher(temp).replaceAll("")
                .replace('đ', 'd')
                .replaceAll("\\s+", " ");
    }
}
