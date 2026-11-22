package com.example.mealoptimizerservice;

import com.google.ortools.Loader;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@Slf4j
@SpringBootApplication
public class MealoptimizerserviceApplication {

    public static void main(String[] args) {
        SpringApplication.run(MealoptimizerserviceApplication.class, args);
    }

    @PostConstruct
    public void initOrToolsNativeLibrary() {
        try {
            Loader.loadNativeLibraries();
            log.info("Đã nạp thành công thư viện C++ Native Google OR-Tools CP-SAT.");
        } catch (Throwable t) {
            log.error("Không thể nạp thư viện JNI OR-Tools. Hãy kiểm tra biến môi trường/glibc trên Docker!", t);
        }
    }
}
