package com.menufood.userservice;

import com.menufood.userservice.entity.User;
import com.menufood.userservice.repository.UserProfileRepository;
import com.menufood.userservice.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
class UserApiTests {
    private static final String PASSWORD = "TestPassword123!";
    private static final String PROFILE = """
            {
              "dateOfBirth": "1995-04-12",
              "gender": "MALE",
              "height": 170,
              "weight": 75,
              "activityLevel": "MODERATE",
              "goal": "LOSE_WEIGHT",
              "targetWeight": 68,
              "allergies": [" tôm ", "tôm"],
              "restrictedIngredients": ["đường"],
              "preferences": ["cá"]
            }
            """;

    @Autowired
    private WebApplicationContext context;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private UserProfileRepository userProfileRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private ObjectMapper objectMapper;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
        userProfileRepository.deleteAll();
        userRepository.deleteAll();
    }

    @Test
    void registerHashesPasswordAndDoesNotExposeIt() throws Exception {
        register("Alice@Example.com");

        User user = userRepository.findByEmail("alice@example.com").orElseThrow();
        assertThat(user.getPasswordHash()).isNotEqualTo(PASSWORD);
        assertThat(passwordEncoder.matches(PASSWORD, user.getPasswordHash())).isTrue();
        assertThat(user.getRole()).isEqualTo("USER");

        mvc.perform(get("/api/users/me").with(httpBasic("ALICE@example.com", PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(user.getId().toString()))
                .andExpect(jsonPath("$.data.password").doesNotExist())
                .andExpect(jsonPath("$.data.passwordHash").doesNotExist());
    }

    @Test
    void duplicateEmailIsCaseInsensitive() throws Exception {
        register("alice@example.com");
        mvc.perform(post("/api/auth/register").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON).content(registration("ALICE@example.com")))
                .andExpect(status().isConflict());
        assertThat(userRepository.count()).isEqualTo(1);
    }

    @Test
    void invalidRegistrationIsRejected() throws Exception {
        mvc.perform(post("/api/auth/register").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"invalid", "password":"short", "fullName":" "}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors.email").exists())
                .andExpect(jsonPath("$.errors.password").exists());
        assertThat(userRepository.count()).isZero();
    }

    @Test
    void rejectsPasswordExceedingBcryptByteLimit() throws Exception {
        mvc.perform(post("/api/auth/register").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registration("alice@example.com").replace(PASSWORD, "ậ".repeat(25))))
                .andExpect(status().isBadRequest());
    }

    @Test
    void personalEndpointsRequireAuthentication() throws Exception {
        mvc.perform(get("/api/users/me")).andExpect(status().isUnauthorized());
        mvc.perform(put("/api/users/me/profile").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON).content(PROFILE))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        register("alice@example.com");
        mvc.perform(get("/api/users/me").with(httpBasic("alice@example.com", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingProfileReturnsNotFound() throws Exception {
        register("alice@example.com");
        mvc.perform(get("/api/users/me/profile").with(httpBasic("alice@example.com", PASSWORD)))
                .andExpect(status().isNotFound());
    }

    @Test
    void createsUpdatesAndReadsProfileWithoutTrustingUserIdHeader() throws Exception {
        register("alice@example.com");
        register("bob@example.com");
        String bobId = userRepository.findByEmail("bob@example.com").orElseThrow().getId().toString();

        mvc.perform(put("/api/users/me/profile").with(csrf())
                        .with(httpBasic("alice@example.com", PASSWORD)).header("X-User-ID", bobId)
                        .contentType(MediaType.APPLICATION_JSON).content(PROFILE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.allergies.length()").value(1))
                .andExpect(jsonPath("$.data.allergies[0]").value("tôm"));

        String updated = PROFILE.replace("\"weight\": 75", "\"weight\": 72")
                .replace("[\" tôm \", \"tôm\"]", "[]");
        mvc.perform(put("/api/users/me/profile").with(csrf())
                        .with(httpBasic("alice@example.com", PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON).content(updated))
                .andExpect(status().isOk());

        mvc.perform(get("/api/users/me/profile").with(httpBasic("alice@example.com", PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.weight").value(72))
                .andExpect(jsonPath("$.data.allergies").isEmpty())
                .andExpect(jsonPath("$.data.preferences[0]").value("cá"));
        mvc.perform(get("/api/users/me/profile").with(httpBasic("bob@example.com", PASSWORD)))
                .andExpect(status().isNotFound());
        assertThat(userProfileRepository.count()).isEqualTo(1);
    }

    @ParameterizedTest
    @ValueSource(strings = {"negativeWeight", "zeroHeight", "minor", "futureBirth", "invalidEnum", "nullList", "blankIngredient", "tooManyDecimals", "missingGoal"})
    void invalidProfileDoesNotWriteData(String invalidCase) throws Exception {
        register("alice@example.com");
        String invalidProfile = switch (invalidCase) {
            case "negativeWeight" -> PROFILE.replace("\"weight\": 75", "\"weight\": -1");
            case "zeroHeight" -> PROFILE.replace("\"height\": 170", "\"height\": 0");
            case "minor" -> PROFILE.replace("1995-04-12", java.time.LocalDate.now().minusYears(17).toString());
            case "futureBirth" -> PROFILE.replace("1995-04-12", java.time.LocalDate.now().plusDays(1).toString());
            case "invalidEnum" -> PROFILE.replace("MODERATE", "UNKNOWN");
            case "nullList" -> PROFILE.replace("[\" tôm \", \"tôm\"]", "null");
            case "blankIngredient" -> PROFILE.replace("[\" tôm \", \"tôm\"]", "[\" \"]");
            case "tooManyDecimals" -> PROFILE.replace("\"weight\": 75", "\"weight\": 75.123");
            case "missingGoal" -> PROFILE.replace("\"goal\": \"LOSE_WEIGHT\",", "");
            default -> throw new IllegalArgumentException(invalidCase);
        };

        mvc.perform(put("/api/users/me/profile").with(csrf())
                        .with(httpBasic("alice@example.com", PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON).content(invalidProfile))
                .andExpect(status().isBadRequest());
        assertThat(userProfileRepository.count()).isZero();
    }

    @Test
    void csrfIsRequiredForWrites() throws Exception {
        mvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isNotEmpty());
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON)
                        .content(registration("alice@example.com")))
                .andExpect(status().isForbidden());

        register("alice@example.com");
        mvc.perform(put("/api/users/me/profile").with(httpBasic("alice@example.com", PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON).content(PROFILE))
                .andExpect(status().isForbidden());
    }

    @Test
    void csrfTokenEndpointSupportsRealRegistrationFlow() throws Exception {
        var result = mvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isOk()).andReturn();
        var token = objectMapper.readTree(result.getResponse().getContentAsString());
        var session = (MockHttpSession) result.getRequest().getSession(false);

        mvc.perform(post("/api/auth/register").session(session)
                        .header(token.get("headerName").asText(), token.get("token").asText())
                        .contentType(MediaType.APPLICATION_JSON).content(registration("alice@example.com")))
                .andExpect(status().isCreated());

        mvc.perform(put("/api/users/me/profile").session(session)
                        .with(httpBasic("alice@example.com", PASSWORD))
                        .header(token.get("headerName").asText(), token.get("token").asText())
                        .contentType(MediaType.APPLICATION_JSON).content(PROFILE))
                .andExpect(status().isOk());
    }

    private void register(String email) throws Exception {
        mvc.perform(post("/api/auth/register").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON).content(registration(email)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.passwordHash").doesNotExist());
    }

    private String registration(String email) {
        return """
                {"email":"%s", "password":"%s", "fullName":"Người dùng thử"}
                """.formatted(email, PASSWORD);
    }
}
