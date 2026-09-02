<a id="english"></a>

# stock-master-bot

**English** | [简体中文](#简体中文)

An auditable investment-thesis monitoring and event research platform for U.S. equities.

## Overview

`stock-master-bot` continuously evaluates whether the reasons behind an investment thesis still hold. When material facts change, it produces timely, deterministic, and traceable events backed by evidence.

The project combines:

- deterministic Python logic for calculations, thresholds, and rule evaluation;
- LLMs for unstructured information extraction, evidence synthesis, and explanation;
- persistent, versioned data for auditability, replay, and historical analysis.

It is not intended to be a generic AI workflow engine or an autonomous stock-picking system.

> **The system does not decide what users should buy. It continuously checks whether their reasons for holding or watching a stock remain valid.**

## Product Direction

General-purpose agents will increasingly provide web search, stock Q&A, filing summaries, scheduled tasks, and report generation. The long-term value of this project therefore comes from domain assets that exist outside the model itself:

1. structured user investment theses and invalidation conditions;
2. point-in-time historical observations and revision history;
3. multi-source data quality assessment and reconciliation;
4. explicit relationships among events, evidence, metrics, and theses;
5. user feedback on usefulness, false positives, and duplicates;
6. reproducible rule evaluations and decision history.

## Thesis Monitoring

A user can define a structured thesis and deterministic conditions for a stock:

```text
Stock: AAPL

Investment thesis:
Services will remain a primary growth driver over the next three years.

Invalidation conditions:
1. Services revenue growth falls below 10% year over year.
2. Services revenue growth slows for two consecutive quarters.
3. Gross margin declines by more than two percentage points.
```

The intended workflow is:

```text
Create an investment thesis
    ↓
Define supporting, risk, and invalidation conditions
    ↓
Collect and normalize market, financial, and event data
    ↓
Calculate metrics and evaluate deterministic rules
    ↓
Create structured events with auditable evidence
    ↓
Use an LLM to summarize, attribute, and explain uncertainty
    ↓
Collect user feedback and update thesis state
    ↓
Build a long-term decision and review history
```

## Defensibility

### User Research State

- investment theses, conditions, monitored metrics, and personalized thresholds;
- thesis versions, status changes, and decision records;
- research context accumulated over long-term use.

### Point-in-Time Data

- distinguish reporting period, publication time, first observation time, and revision time;
- ensure historical evaluation only uses information available at that time;
- support replay, backtesting, and report reproduction without look-ahead bias.

### Multi-Source Quality and Reconciliation

- retain provider, metric definition, observation time, and source field;
- compare conflicting values and produce explainable quality assessments;
- preserve raw inputs, normalized observations, and revision history.

### Events and Evidence

- connect companies, metrics, filings, events, evidence, conditions, and theses;
- identify which thesis is affected by a newly detected event;
- trace conclusions to source records, calculation inputs, formulas, and rule versions.

### Feedback Loop

- record whether an event was useful, a false positive, a duplicate, or irrelevant;
- measure precision, false-positive rate, evidence quality, and notification value;
- improve rules, thresholds, and delivery based on actual user feedback.

## Deterministic Engineering and AI Boundaries

The system separates facts, rule decisions, and model-generated interpretations:

```text
Fact layer:
Raw market data, financial observations, filings, and source evidence

Rule layer:
Returns, trends, thresholds, and thesis conditions calculated by deterministic code

AI layer:
Unstructured extraction, evidence synthesis, event explanation, and report wording
```

LLMs must not perform authoritative numeric calculations, trigger thresholds, or make trading decisions. Models can be replaced or upgraded while normalized data, deterministic rules, evidence chains, and user research state remain stable.

A qualified event report should include:

- verified facts and their effective dates;
- the triggered rule and calculation inputs;
- the affected thesis or condition;
- source evidence, citations, and source versions;
- model-generated interpretation and uncertainty;
- rule, prompt, and model versions.

## MVP Scope

The first usable release focuses on a narrow end-to-end workflow:

```text
User creates a stock thesis and monitoring condition
        ↓
System collects and persists normalized data
        ↓
Deterministic rules evaluate metric changes
        ↓
System creates a structured event and evidence records
        ↓
Web console displays the event and its reasoning
        ↓
User marks it as useful, false positive, duplicate, or irrelevant
        ↓
LLM explains facts that have already been deterministically confirmed
```

Initial MVP capabilities:

- normalized U.S. equity daily bars, PE, PB, and EBITDA observations;
- price, volume, and valuation-change rules;
- user-defined investment theses and thresholds;
- rule evaluation history;
- structured events, evidence details, and feedback;
- AI explanations grounded in deterministic events.

Later phases may add SEC filings, company announcements, earnings calls, news clustering, thesis version history, and point-in-time backtesting.

## Architecture

```text
External data providers
        ↓
Collection, validation, and normalization
        ↓
Market and fundamental persistence
        ↓
Deterministic metric calculation
        ↓
Investment thesis and condition evaluation
        ↓
Structured event and evidence generation
        ├── Fast path: Web/API/notifications
        └── Slow path: LLM explanation and report generation
        ↓
User feedback and thesis state history
```

The MVP is designed as a modular monolith. Redis, Celery, a vector database, and distributed workers should only be introduced when operational requirements justify them.

See [`architecture.svg`](architecture.svg) for the detailed system diagram.

## Technology Stack

### Current foundation

- Python 3.12+
- Pydantic 2
- HTTPX and `yfinance`
- PostgreSQL 16
- SQLAlchemy 2 async
- asyncpg
- Alembic
- Docker Compose for local PostgreSQL where available

### Planned MVP delivery layer

- FastAPI
- Jinja2 and HTMX, or another lightweight web UI
- a deterministic rule engine implemented in Python
- scheduled daily ingestion
- an LLM integration added after deterministic events are stable

### Deferred until required

- Celery and Redis
- streaming market ingestion
- vector databases and RAG infrastructure
- distributed workflow orchestration
- multi-agent execution

## Current Implementation Status

Implemented:

- Alpha Vantage, Yahoo Finance, and Finnhub data source adapters;
- normalized `DailyBar` and `CompanyFundamentals` models;
- PostgreSQL configuration and async SQLAlchemy sessions;
- market, fundamental snapshot, and anomaly event ORM tables;
- Alembic database migrations;
- repository-level PostgreSQL upserts and queries;
- stock ingestion service;
- investment thesis, condition, rule evaluation, event, evidence, and feedback domain models;
- ORM definitions for the thesis-monitoring domain.

In progress:

- migration for thesis-monitoring domain tables;
- thesis and event repositories;
- deterministic metric and rule evaluation services;
- FastAPI and web console.

Not yet implemented:

- production authentication and authorization;
- AI explanations and report generation;
- notification delivery;
- point-in-time raw artifact storage and revision tracking;
- SEC filing and earnings-call ingestion.

## Project Structure

```text
.
├── alembic/                         # Database migration environment
│   └── versions/                    # Versioned migration scripts
├── app/
│   ├── data_sources/                # Provider adapters and normalized models
│   ├── database/                    # SQLAlchemy tables, sessions, and repositories
│   ├── domain/                      # Thesis, rule, event, evidence, and feedback models
│   └── services/                    # Application workflow services
├── architecture.svg                # Detailed architecture diagram
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Security Principles

- secrets are loaded from environment variables and never committed;
- SQL values are bound through SQLAlchemy rather than string concatenation;
- tenant-owned records include ownership checks and database constraints;
- external URLs must use HTTPS and approved hosts;
- provider responses and LLM outputs are treated as untrusted input;
- raw evidence references are not executed as URLs;
- numeric facts and rule decisions remain deterministic and auditable.

## Development

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the fast backend checks with `python -m pytest -m "not integration"` and `ruff check app tests`. For the isolated PostgreSQL integration test:

```bash
docker compose -f docker-compose.test.yml up -d --wait
RUN_POSTGRES_INTEGRATION=1 POSTGRES_USER=stock_master_test \
  POSTGRES_PASSWORD=stock_master_test_password POSTGRES_DB=stock_master_test \
  POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 python -m pytest
docker compose -f docker-compose.test.yml down
```

Configure local secrets in `.env`. Never commit this file.

When PostgreSQL is available, apply migrations and start the API with:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The protected Next.js web console lives in `web/`. Configure its server-only environment and start it separately:

```bash
cd web
cp .env.example .env.local
npm ci
npm run dev
```

Run `npm run check` to execute linting, type checking, coverage tests, and the production build.

Set `BACKEND_API_TOKEN` to the same secret as the backend `API_BEARER_TOKEN`. `WEB_ADMIN_PASSWORD` and `WEB_SESSION_SECRET` protect browser access; none of these values are exposed to client-side JavaScript.

This project is under active development and is not financial advice or a trading system.

---

<a id="简体中文"></a>

# stock-master-bot（简体中文）

[English](#english) | **简体中文**

一个面向美股的、可审计的投资论点监控与事件研究平台。

## 项目简介

`stock-master-bot` 持续检查用户投资论点背后的理由是否仍然成立。当关键事实发生变化时，系统生成及时、确定性且可追溯的事件，并提供对应证据。

项目结合：

- 使用确定性 Python 代码完成数值计算、阈值判断和规则评估；
- 使用 LLM 完成非结构化信息提取、证据归纳和解释；
- 使用持久化和版本化数据支持审计、重放与历史分析。

项目的最终定位不是通用 AI 工作流引擎，也不是自动选股系统。

> **系统不替用户决定买什么，而是持续检查用户持有或关注一只股票的理由是否仍然有效。**

## 产品方向

随着通用 Agent 能力提升，联网搜索、股票问答、财报总结、定时任务和报告生成会逐渐成为基础能力。因此，本项目的长期价值来自模型之外持续积累的领域资产：

1. 结构化的用户投资论点及失效条件；
2. 时间点正确的历史观察值与修订历史；
3. 多数据源质量评估与冲突仲裁；
4. 事件、证据、指标和投资论点之间的明确关系；
5. 用户对事件价值、误报和重复的反馈；
6. 可复现的规则评估与决策历史。

## 投资论点监控

用户可以为股票定义结构化论点及确定性条件：

```text
股票：AAPL

投资论点：
服务业务将在未来三年继续成为主要增长动力。

失效条件：
1. 服务收入同比增速低于 10%；
2. 服务收入增速连续两个季度放缓；
3. 毛利率下降超过 2 个百分点。
```

目标工作流：

```text
创建投资论点
    ↓
定义支持、风险和失效条件
    ↓
采集并标准化市场、财务与事件数据
    ↓
计算指标并执行确定性规则
    ↓
生成带有可审计证据的结构化事件
    ↓
使用 LLM 归纳、归因并解释不确定性
    ↓
收集用户反馈并更新论点状态
    ↓
形成长期决策和复盘历史
```

## 护城河

### 用户研究状态

- 投资论点、条件、关注指标和个性化阈值；
- 论点版本、状态变化和决策记录；
- 用户长期积累的研究上下文。

### 时间点正确的数据

- 区分报告期间、公开时间、首次观察时间和修订时间；
- 保证历史评估只使用当时已经公开的信息；
- 支持无未来数据泄漏的重放、回测和报告复现。

### 多数据源质量与仲裁

- 保存供应商、指标口径、观察时间和来源字段；
- 比较冲突数值并给出可解释的质量评估；
- 保留原始输入、标准化观察值和修订历史。

### 事件与证据关系

- 连接公司、指标、财报、事件、证据、条件和投资论点；
- 判断新事件影响了用户的哪条投资论点；
- 将结论追溯到原始记录、计算输入、公式和规则版本。

### 用户反馈闭环

- 记录事件是否有价值、误报、重复或不相关；
- 评估准确率、误报率、证据质量和通知价值；
- 根据真实反馈优化规则、阈值和交付方式。

## 确定性工程与 AI 边界

系统严格区分事实、规则判断和模型解释：

```text
事实层：
原始行情、财务观察值、财报和来源证据

规则层：
由确定性代码计算的收益率、趋势、阈值和论点条件

AI 层：
非结构化信息提取、证据归纳、事件解释和报告表达
```

LLM 不负责权威数值计算、阈值触发或交易决策。模型可以被替换和升级，但标准化数据、确定性规则、证据链和用户研究状态保持稳定。

一份合格的事件报告应包括：

- 已验证事实及其生效时间；
- 被触发的规则和计算输入；
- 受影响的投资论点或条件；
- 原始证据、引用位置和来源版本；
- 模型解释及其不确定性；
- 规则、提示词和模型版本。

## MVP 范围

第一个可用版本聚焦于一条狭窄但完整的业务闭环：

```text
用户创建股票论点和监控条件
        ↓
系统采集并持久化标准化数据
        ↓
确定性规则评估指标变化
        ↓
系统创建结构化事件和证据记录
        ↓
Web 控制台展示事件和触发依据
        ↓
用户标记有价值、误报、重复或不相关
        ↓
LLM 对已经确定性确认的事实进行解释
```

初始 MVP 能力：

- 标准化美股日线、PE、PB 和 EBITDA 数据；
- 价格、成交量和估值变化规则；
- 用户自定义投资论点和阈值；
- 规则评估历史；
- 结构化事件、证据详情和反馈；
- 基于确定性事件的 AI 解释。

后续阶段可以加入 SEC 财报、公司公告、电话会议、新闻聚类、论点版本历史和时间点正确的历史回测。

## 架构

```text
外部数据供应商
        ↓
采集、校验与标准化
        ↓
行情和基本面持久化
        ↓
确定性指标计算
        ↓
投资论点与条件评估
        ↓
结构化事件与证据生成
        ├── 快速链路：Web/API/通知
        └── 慢速链路：LLM 解释与报告生成
        ↓
用户反馈与论点状态历史
```

MVP 采用模块化单体。只有在实际运行需求出现后，才引入 Redis、Celery、向量数据库和分布式 Worker。

详细系统图见 [`architecture.svg`](architecture.svg)。

## 技术栈

### 当前基础

- Python 3.12+
- Pydantic 2
- HTTPX 与 `yfinance`
- PostgreSQL 16
- SQLAlchemy 2 异步模式
- asyncpg
- Alembic
- 在可用环境中使用 Docker Compose 启动本地 PostgreSQL

### 计划中的 MVP 交付层

- FastAPI
- Jinja2 与 HTMX，或其他轻量 Web UI
- 使用 Python 实现的确定性规则引擎
- 每日定时采集
- 在确定性事件稳定后接入 LLM

### 暂缓引入

- Celery 与 Redis
- 流式行情接入
- 向量数据库与 RAG 基础设施
- 分布式工作流编排
- 多 Agent 执行

## 当前实现状态

已经实现：

- Alpha Vantage、Yahoo Finance 和 Finnhub 数据源适配器；
- 标准化 `DailyBar` 和 `CompanyFundamentals` 模型；
- PostgreSQL 配置与异步 SQLAlchemy 会话；
- 行情、基本面快照和异动事件 ORM 表；
- Alembic 数据库迁移；
- Repository 层 PostgreSQL Upsert 和查询；
- 股票数据采集服务；
- 投资论点、条件、规则评估、事件、证据和反馈领域模型；
- 投资论点监控领域 ORM 定义。

正在实现：

- 投资论点监控领域表迁移；
- 投资论点和事件 Repository；
- 确定性指标与规则评估服务；
- FastAPI 与 Web 控制台。

尚未实现：

- 生产级认证与授权；
- AI 解释和报告生成；
- 通知交付；
- 时间点正确的原始材料存储与修订跟踪；
- SEC 财报和电话会议接入。

## 项目结构

```text
.
├── alembic/                         # 数据库迁移环境
│   └── versions/                    # 版本化迁移脚本
├── app/
│   ├── data_sources/                # 数据源适配器和标准模型
│   ├── database/                    # SQLAlchemy 表、会话和 Repository
│   ├── domain/                      # 论点、规则、事件、证据和反馈模型
│   └── services/                    # 应用工作流服务
├── architecture.svg                # 详细架构图
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 安全原则

- 密钥只从环境变量读取，禁止提交到版本库；
- SQL 值通过 SQLAlchemy 参数绑定，禁止拼接用户输入；
- 多租户记录包含所有权检查和数据库约束；
- 外部 URL 必须使用 HTTPS 和允许的主机；
- 供应商响应和 LLM 输出均作为不可信输入处理；
- 原始证据引用不能被直接当作 URL 执行；
- 数值事实与规则判断保持确定性和可审计性。

## 开发

创建并激活虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

通过 `python -m pytest -m "not integration"` 和 `ruff check app tests` 运行后端快速检查。真实 PostgreSQL 集成测试使用隔离数据库：

```bash
docker compose -f docker-compose.test.yml up -d --wait
RUN_POSTGRES_INTEGRATION=1 POSTGRES_USER=stock_master_test \
  POSTGRES_PASSWORD=stock_master_test_password POSTGRES_DB=stock_master_test \
  POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 python -m pytest
docker compose -f docker-compose.test.yml down
```

在 `.env` 中配置本地密钥，禁止提交该文件。

PostgreSQL 可用时执行迁移并启动 API：

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

受保护的 Next.js Web 控制台位于 `web/`，复制服务端环境变量模板后单独启动：

```bash
cd web
cp .env.example .env.local
npm ci
npm run dev
```

运行 `npm run check` 可依次执行 lint、类型检查、覆盖率测试和生产构建。

`BACKEND_API_TOKEN` 应与后端的 `API_BEARER_TOKEN` 保持一致。`WEB_ADMIN_PASSWORD` 和 `WEB_SESSION_SECRET` 用于保护浏览器访问，以上值均不会暴露给客户端 JavaScript。

项目仍在积极开发中，不构成投资建议，也不是自动交易系统。
