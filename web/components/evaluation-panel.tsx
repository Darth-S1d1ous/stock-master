"use client";

import { useActionState } from "react";
import { evaluateThesisAction, type EvaluationState } from "@/app/(console)/theses/evaluate-actions";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { metricLabels, operatorLabels } from "@/lib/constants";
import { formatMetric } from "@/lib/format";

const initialState: EvaluationState = { ok: false };

export function EvaluationPanel({ thesisId }: { thesisId: string }) {
  const [state, action] = useActionState(evaluateThesisAction, initialState);
  return <div className="card">
    <div className="card-header"><div><p className="eyebrow">Deterministic check</p><h2>Run monitoring</h2></div></div>
    <div className="card-body">
      <FormMessage state={state} />
      <form action={action} className="form-grid">
        <input type="hidden" name="thesis_id" value={thesisId} />
        <div className="field"><label>Data source</label><select name="source" defaultValue="alpha_vantage"><option value="alpha_vantage">Alpha Vantage</option><option value="finnhub">Finnhub</option><option value="yahoo_finance">Yahoo Finance</option></select></div>
        <div className="field"><label>Price adjustment</label><select name="adjustment" defaultValue="raw"><option value="raw">Raw price</option><option value="split_adjusted">Split adjusted</option><option value="total_return">Total return</option></select></div>
        <div className="field field-full"><SubmitButton pendingText="Calculating…">Run deterministic evaluation</SubmitButton></div>
      </form>
      {state.result ? <div style={{ marginTop: 24 }}>
        <div className="result-grid"><div className="result-stat"><span className="subtle">Evaluated conditions</span><strong>{state.result.evaluation_count}</strong></div><div className="result-stat"><span className="subtle">Matched conditions</span><strong>{state.result.matched_count}</strong></div><div className="result-stat"><span className="subtle">Related events</span><strong>{state.result.event_count}</strong></div></div>
        {state.result.conditions.map(({ condition, evaluation }) => <div className="condition" key={condition.id}><div className="condition-top"><div><strong>{condition.name}</strong><p className="subtle">{metricLabels[evaluation.metric]} · Data as of {evaluation.data_as_of}</p></div><span className={`badge ${evaluation.matched ? "badge-warning" : "badge-resolved"}`}>{evaluation.matched ? "Matched" : "Not matched"}</span></div><div className="rule">{formatMetric(evaluation.observed_value, evaluation.metric)} {operatorLabels[evaluation.operator]} {formatMetric(evaluation.threshold, evaluation.metric)} · {evaluation.consecutive_periods_matched}/{evaluation.consecutive_periods_required} periods</div></div>)}
      </div> : null}
    </div>
  </div>;
}
