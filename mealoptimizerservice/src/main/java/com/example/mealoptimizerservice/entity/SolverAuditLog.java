package com.example.mealoptimizerservice.entity;

import com.example.mealoptimizerservice.entity.enums.*;
import jakarta.persistence.*;
import lombok.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

// --- FILE: SolverAuditLog.java ---
@Entity
@Table(name = "solver_audit_logs")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SolverAuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id")
    private Long userId;

    @Column(name = "operation_type", nullable = false, length = 50)
    private String operationType; // DAILY_GEN, PROFILE_GEN, SWAP_DISH, REBALANCE, DRY_RUN

    @Enumerated(EnumType.STRING)
    @Column(name = "solver_status", nullable = false, length = 30)
    private SolverRunStatus solverStatus;

    @Column(name = "candidate_count")
    private Integer candidateCount;

    @Column(name = "solve_time_ms")
    private Long solveTimeMs;

    @Column(name = "objective_value")
    private Double objectiveValue;

    @Column(name = "cal_deviation_kcal", precision = 6, scale = 2)
    private BigDecimal calDeviationKcal;

    @Column(name = "carb_deviation_g", precision = 6, scale = 2)
    private BigDecimal carbDeviationG;

    @Builder.Default
    @Column(name = "executed_at")
    private LocalDateTime executedAt = LocalDateTime.now();
}
