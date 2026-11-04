package com.menufood.userservice.config;

import com.menufood.userservice.dto.response.ErrorResponse;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Map;

@Configuration
public class SecurityConfig {
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http, ObjectMapper objectMapper) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/register").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic.authenticationEntryPoint((request, response, exception) -> {
                    response.setHeader("WWW-Authenticate", "Basic realm=\"MenuFood\"");
                    writeError(response, objectMapper, 401, "Vui lòng đăng nhập bằng email và mật khẩu", request.getRequestURI());
                }))
                .csrf(Customizer.withDefaults())
                .exceptionHandling(errors -> errors.accessDeniedHandler((request, response, exception) ->
                        writeError(response, objectMapper, 403, "Không có quyền truy cập hoặc thiếu CSRF token", request.getRequestURI())));
        return http.build();
    }

    private void writeError(HttpServletResponse response, ObjectMapper objectMapper, int status,
                            String message, String path) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(
                new ErrorResponse(Instant.now(), status, message, path, Map.of())));
    }
}
