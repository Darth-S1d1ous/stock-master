"""mermaid
sequenceDiagram
    autonumber

    actor Client
    participant API as FastAPI Router
    participant Auth as Authentication Dependency
    participant Tx as Database Session
    participant ThesisRepo as Thesis Repository
    participant StockRepo as Stock Data Repository
    participant Monitor as Thesis Monitoring Service
    participant Registry as Metric Registry
    participant Calculator as Metric Calculator
    participant RuleEngine as Rule Engine
    participant DB as PostgreSQL

    Note over Client,DB: Create Investment Thesis

    Client->>API: POST /api/v1/theses<br/>Authorization: Bearer token
    API->>Auth: Validate bearer token
    Auth-->>API: Authenticated user ID
    API->>Tx: Open request transaction
    API->>API: Build InvestmentThesis
    API->>ThesisRepo: create_thesis(thesis)
    ThesisRepo->>DB: INSERT investment_theses
    DB-->>ThesisRepo: Created thesis
    ThesisRepo-->>API: InvestmentThesis
    API->>Tx: Commit transaction
    API-->>Client: 201 Created<br/>InvestmentThesisResponse

    Note over Client,DB: Create Monitoring Condition

    Client->>API: POST /api/v1/theses/{id}/conditions<br/>Condition definition
    API->>Auth: Validate bearer token
    Auth-->>API: Authenticated user ID
    API->>Tx: Open request transaction
    API->>API: Build ThesisCondition
    API->>ThesisRepo: create_condition(condition)
    ThesisRepo->>DB: SELECT owned thesis by user ID
    DB-->>ThesisRepo: Investment thesis

    alt Thesis does not exist or is not owned
        ThesisRepo-->>API: ResourceNotFoundError
        API->>Tx: Roll back transaction
        API-->>Client: 404 Thesis Not Found
    else Thesis is owned
        ThesisRepo->>DB: INSERT thesis_conditions
        DB-->>ThesisRepo: Created condition
        ThesisRepo-->>API: ThesisCondition
        API->>Tx: Commit transaction
        API-->>Client: 201 Created<br/>ThesisConditionResponse
    end

    Note over Client,DB: Run Deterministic Thesis Monitoring

    Client->>API: POST /api/v1/theses/{id}/evaluate<br/>Source and price adjustment
    API->>Auth: Validate bearer token

    alt Token is missing or invalid
        Auth-->>Client: 401 Authentication Required
    else Token is valid
        Auth-->>API: Authenticated user ID
        API->>Tx: Open request transaction
        API->>Monitor: evaluate_thesis(user ID, thesis ID, source)
        Monitor->>ThesisRepo: require_thesis(user ID, thesis ID)
        ThesisRepo->>DB: SELECT owned thesis
        DB-->>ThesisRepo: Investment thesis
        ThesisRepo-->>Monitor: InvestmentThesis

        alt Thesis is archived or invalidated
            Monitor-->>API: ThesisNotMonitorableError
            API->>Tx: Roll back transaction
            API-->>Client: 409 Thesis Not Monitorable
        else Thesis is monitorable
            Monitor->>ThesisRepo: list_enabled_conditions(user ID, thesis ID)
            ThesisRepo->>DB: SELECT enabled conditions
            DB-->>ThesisRepo: Thesis conditions
            ThesisRepo-->>Monitor: Enabled conditions

            loop For each enabled condition
                Monitor->>Registry: get_metric_definition(metric)
                Registry-->>Monitor: Input kind, required count, calculator

                alt Metric requires daily bars
                    Monitor->>StockRepo: get_recent_daily_bars(symbol, source, adjustment, limit)
                    StockRepo->>DB: SELECT normalized daily bars
                    DB-->>StockRepo: Daily bar rows
                    StockRepo-->>Monitor: DailyBar sequence
                    Monitor->>Calculator: calculate_daily(bars)
                else Metric requires fundamentals
                    Monitor->>StockRepo: get_company_fundamentals_history(symbol, source, limit)
                    StockRepo->>DB: SELECT fundamental snapshots
                    DB-->>StockRepo: Fundamental rows
                    StockRepo-->>Monitor: CompanyFundamentals sequence
                    Monitor->>Calculator: calculate_fundamentals(snapshots)
                end

                Calculator-->>Monitor: MetricResult<br/>value, date, observation IDs

                Monitor->>ThesisRepo: list_prior_evaluations(condition, version, date)
                ThesisRepo->>DB: SELECT prior rule evaluations
                DB-->>ThesisRepo: Evaluation history
                ThesisRepo-->>Monitor: Prior evaluations

                Monitor->>RuleEngine: evaluate_condition(thesis, condition, metric, history)
                RuleEngine-->>Monitor: RuleEvaluation

                Monitor->>ThesisRepo: save_rule_evaluation(evaluation)
                ThesisRepo->>DB: INSERT evaluation ON CONFLICT DO NOTHING

                alt Evaluation already exists
                    ThesisRepo->>DB: SELECT existing evaluation
                    DB-->>ThesisRepo: Existing evaluation
                    ThesisRepo-->>Monitor: Existing RuleEvaluation
                else New evaluation
                    DB-->>ThesisRepo: Created evaluation
                    ThesisRepo-->>Monitor: New RuleEvaluation
                end

                alt Condition is not matched
                    Monitor->>Monitor: Return evaluation without event
                else Condition is matched
                    Monitor->>Monitor: Build DomainEvent
                    Monitor->>Monitor: Build evidence from observation IDs
                    Monitor->>ThesisRepo: save_event_with_evidence(event, evidence)
                    ThesisRepo->>DB: INSERT event ON CONFLICT DO NOTHING

                    alt Event already exists
                        ThesisRepo->>DB: SELECT existing event and evidence
                        DB-->>ThesisRepo: Existing event and evidence
                    else New event
                        ThesisRepo->>DB: INSERT event evidence
                        DB-->>ThesisRepo: Created event and evidence
                    end

                    ThesisRepo-->>Monitor: DomainEvent and EventEvidence
                end
            end

            Monitor-->>API: ThesisMonitoringResult
            API->>Tx: Commit transaction
            API-->>Client: 200 OK<br/>ThesisMonitoringResponse
        end
    end

    Note over Client,DB: Any unhandled failure rolls back the complete request transaction
"""