"""
Transform:
InvestmentThesis
+ ThesisCondition
+ MetricResult
+ history RuleEvaluation

to a new RuleEvaluation
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.domain.event_models import RuleEvaluation
from app.domain.metric_calculator import MetricResult
from app.domain.thesis_models import (
    ComparisonOperator,
    InvestmentThesis,
    ThesisCondition,
)


class RuleEvaluationError(ValueError):
    """Raised when a rule evaluation cannot be completed."""

"""
Evaluate one thesis condition against one deterministic metric result.

The returned matched value represents the final condition state after
applying the configured consecutive-period requirement.
"""
def evaluate_condition(
    thesis: InvestmentThesis,
    condition: ThesisCondition,
    metric_result: MetricResult,
    prior_evaluations: Sequence[RuleEvaluation] = (),
) -> RuleEvaluation:

    _validate_relationships(thesis=thesis, condition=condition, metric_result=metric_result)

    if not condition.enabled:
        raise RuleEvaluationError("condition is disabled")
    
    # in the current period, whether the metric result value matches the pre-defined rule
    current_period_matches = compare_values(
        observed_value=metric_result.value,
        threshold=condition.threshold,
        operator=condition.operator
    )

    consecutive_periods_matched = _calculate_consecutive_periods(
        thesis=thesis,
        condition=condition,
        metric_result=metric_result,
        current_period_matches=current_period_matches,
        prior_evaluations=prior_evaluations
    )

    condition_matched = (consecutive_periods_matched >= condition.consecutive_periods)

    return RuleEvaluation(
        user_id=condition.user_id,
        thesis_id=condition.thesis_id,
        condition_id=condition.id,
        symbol=thesis.symbol,
        metric=condition.metric,
        operator=condition.operator,
        observed_value=metric_result.value,
        threshold=condition.threshold,
        matched=condition_matched,
        consecutive_periods_required=(
            condition.consecutive_periods
        ),
        consecutive_periods_matched=(
            consecutive_periods_matched
        ),
        rule_version=condition.version,
        data_as_of=metric_result.data_as_of,
        observation_ids=metric_result.observation_ids,
    )

def compare_values(
    observed_value: Decimal,
    threshold: Decimal,
    operator: ComparisonOperator,
) -> bool:

    match operator:
        case ComparisonOperator.GREATER_THAN:
            return observed_value > threshold
        case ComparisonOperator.GREATER_THAN_OR_EQUAL:
            return observed_value >= threshold
        case ComparisonOperator.LESS_THAN:
            return observed_value < threshold
        case ComparisonOperator.LESS_THAN_OR_EQUAL:
            return observed_value <= threshold

def _validate_relationships(
    thesis: InvestmentThesis,
    condition: ThesisCondition,
    metric_result: MetricResult,
) -> None:
    if condition.thesis_id != thesis.id:
        raise RuleEvaluationError("condition is not associated with thesis")
    if condition.user_id != thesis.user_id:
        raise RuleEvaluationError("condition is not associated with user")
    if condition.metric != metric_result.metric:
        raise RuleEvaluationError("condition is not associated with metric")
    if not metric_result.observation_ids:
        raise RuleEvaluationError("metric result has no observation IDs")

def _calculate_consecutive_periods(
    thesis: InvestmentThesis,
    condition: ThesisCondition,
    metric_result: MetricResult,
    current_period_matches: bool,
    prior_evaluations: Sequence[RuleEvaluation],
) -> int:
    if not current_period_matches:
        return 0
    if condition.consecutive_periods == 1:
        return 1

    ordered_history = _validate_and_order_history(
        thesis=thesis,
        condition=condition,
        current_data_as_of=metric_result.data_as_of,
        prior_evaluations=prior_evaluations
    )

    if not ordered_history:
        return 1

    previous = ordered_history[-1]

    if previous.consecutive_periods_matched == 0:
        return 1

    return min(previous.consecutive_periods_matched + 1, condition.consecutive_periods)

def _validate_and_order_history(
    thesis: InvestmentThesis,
    condition: ThesisCondition,
    current_data_as_of: date,
    prior_evaluations: Sequence[RuleEvaluation],
) -> list[RuleEvaluation]:
    ordered = sorted(prior_evaluations, key=lambda evaluation: (evaluation.data_as_of, evaluation.evaluated_at))

    seen_dates: set[date] = set()

    for evaluation in ordered:
        if evaluation.user_id != condition.user_id:
            raise RuleEvaluationError("evaluation is not associated with user")
        if evaluation.thesis_id != thesis.id:
            raise RuleEvaluationError("evaluation is not associated with thesis")
        if evaluation.condition_id != condition.id:
            raise RuleEvaluationError("evaluation is not associated with condition")
        if evaluation.rule_version != condition.version:
            raise RuleEvaluationError("evaluation is not associated with condition version")
        if evaluation.data_as_of >= current_data_as_of:
            raise RuleEvaluationError(
                "prior evaluation must precede the current data date"
            )
        if evaluation.data_as_of in seen_dates:
            raise RuleEvaluationError("Prior evaluations must contain at most one result per date")

        seen_dates.add(evaluation.data_as_of)

    return ordered