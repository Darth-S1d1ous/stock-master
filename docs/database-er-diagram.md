# 数据库 ER 图

以下 ER 图描述本轮后端闭环完成后的目标结构。`anomaly_events` 为旧版兼容表，不参与新业务关系。

```mermaid
erDiagram
    investment_theses {
        uuid id PK
        uuid user_id
        varchar symbol
        varchar title
        text description
        varchar status
        int version
        timestamptz created_at
        timestamptz updated_at
    }

    thesis_status_history {
        uuid id PK
        uuid thesis_id FK
        uuid user_id
        varchar from_status
        varchar to_status
        varchar reason
        uuid triggering_event_id FK
        timestamptz changed_at
    }

    thesis_conditions {
        uuid id PK
        uuid thesis_id FK
        uuid user_id
        varchar name
        varchar kind
        varchar metric
        varchar operator
        numeric threshold
        int consecutive_periods
        boolean enabled
        int version
        timestamptz created_at
        timestamptz updated_at
    }

    thesis_condition_versions {
        uuid id PK
        uuid condition_id FK
        uuid thesis_id
        uuid user_id
        int version
        varchar name
        text description
        varchar kind
        varchar metric
        varchar operator
        numeric threshold
        int consecutive_periods
        boolean enabled
        timestamptz created_at
    }

    daily_bars {
        bigint id PK
        uuid observation_id UK
        varchar symbol
        date trading_date
        numeric open
        numeric high
        numeric low
        numeric close
        bigint volume
        varchar currency
        varchar adjustment
        varchar source
        timestamptz received_at
        timestamptz created_at
    }

    fundamental_snapshots {
        bigint id PK
        uuid observation_id UK
        varchar symbol
        date snapshot_date
        date latest_quarter
        numeric pe_ratio
        numeric price_to_book_ratio
        numeric ebitda
        varchar currency
        varchar source
        timestamptz received_at
        timestamptz created_at
    }

    rule_evaluations {
        uuid id PK
        uuid user_id
        uuid thesis_id FK
        uuid condition_id FK
        varchar symbol
        varchar metric
        varchar operator
        numeric observed_value
        numeric threshold
        boolean matched
        int rule_version
        date data_as_of
        timestamptz evaluated_at
        uuid_array observation_ids
    }

    domain_events {
        uuid id PK
        uuid user_id
        uuid thesis_id FK
        uuid condition_id FK
        uuid evaluation_id FK,UK
        varchar symbol
        varchar event_type
        varchar severity
        varchar status
        text title
        text summary
        date occurred_on
        timestamptz detected_at
        int rule_version
    }

    event_evidence {
        uuid id PK
        uuid event_id FK
        uuid user_id
        varchar evidence_type
        varchar source
        uuid source_record_id
        varchar source_reference
        varchar metric
        numeric observed_value
        date data_as_of
        timestamptz observed_at
    }

    event_feedback {
        uuid id PK
        uuid event_id FK
        uuid user_id
        varchar feedback_type
        text comment
        timestamptz created_at
    }

    ingestion_runs {
        uuid id PK
        varchar source
        varchar mode
        varchar status
        int requested_count
        int succeeded_count
        int failed_count
        timestamptz started_at
        timestamptz completed_at
    }

    ingestion_run_items {
        uuid id PK
        uuid run_id FK
        varchar symbol
        varchar status
        int daily_bars_processed
        date fundamental_snapshot_date
        varchar error_code
        text error_message
        timestamptz started_at
        timestamptz completed_at
    }

    anomaly_events {
        bigint id PK
        varchar symbol
        date trading_date
        varchar event_type
        varchar severity
        jsonb evidence
        timestamptz created_at
    }

    investment_theses ||--o{ thesis_conditions : owns
    investment_theses ||--o{ thesis_status_history : records
    thesis_conditions ||--|{ thesis_condition_versions : versions
    investment_theses ||--o{ rule_evaluations : evaluates
    thesis_conditions ||--o{ rule_evaluations : produces
    rule_evaluations ||--o| domain_events : triggers
    investment_theses ||--o{ domain_events : groups
    thesis_conditions ||--o{ domain_events : explains
    domain_events ||--o{ event_evidence : supports
    domain_events ||--o{ event_feedback : receives
    domain_events o|--o{ thesis_status_history : triggers
    ingestion_runs ||--o{ ingestion_run_items : contains
```

## 图例与边界

- `PK`：主键；`FK`：外键；`UK`：唯一键。
- `investment_theses` 和 `thesis_conditions` 是当前状态投影。
- `thesis_status_history`、`thesis_condition_versions`、`event_feedback` 是追加式历史。
- `ingestion_runs` 与 `ingestion_run_items` 记录 cron/CLI 执行结果，不保存 API 密钥或完整异常堆栈。
- `rule_evaluations.observation_ids` 当前引用 `daily_bars` 或 `fundamental_snapshots` 的 `observation_id`；因来源跨表，本轮不建立数据库外键。
- `anomaly_events` 是旧版孤立表；新监控链路只写入 `domain_events`。
