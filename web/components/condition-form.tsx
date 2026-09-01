"use client";

import { useActionState } from "react";
import { createConditionAction, updateConditionAction } from "@/app/(console)/theses/actions";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { conditionKindLabels, metricOptions, operatorOptions } from "@/lib/constants";
import { INITIAL_ACTION_STATE } from "@/lib/errors";
import type { ThesisCondition } from "@/types/domain";

export function ConditionForm({ thesisId, condition }: { thesisId: string; condition?: ThesisCondition }) {
  const [state, action] = useActionState(condition ? updateConditionAction : createConditionAction, INITIAL_ACTION_STATE);
  return (
    <form action={action}>
      <FormMessage state={state} />
      <input type="hidden" name="thesis_id" value={thesisId} />
      {condition ? <><input type="hidden" name="condition_id" value={condition.id} /><input type="hidden" name="expected_version" value={condition.version} /></> : null}
      <div className="form-grid">
        <div className="field field-full"><label>Condition name</label><input name="name" defaultValue={condition?.name} maxLength={200} required /></div>
        <div className="field"><label>Signal type</label><select name="kind" defaultValue={condition?.kind ?? "risk"}>{Object.entries(conditionKindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div className="field"><label>Monitored metric</label><select name="metric" defaultValue={condition?.metric ?? "daily_price_change_percent"}>{metricOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div className="field"><label>Comparison operator</label><select name="operator" defaultValue={condition?.operator ?? "less_than_or_equal"}>{operatorOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div className="field"><label>Threshold</label><input name="threshold" type="number" step="any" defaultValue={condition?.threshold ?? "-5"} required /></div>
        <div className="field"><label>Consecutive periods</label><input name="consecutive_periods" type="number" min={1} max={12} defaultValue={condition?.consecutive_periods ?? 1} required /></div>
        <div className="field"><label><input name="enabled" type="checkbox" defaultChecked={condition?.enabled ?? true} style={{ width: "auto", marginRight: 8 }} />Enable this condition</label></div>
        <div className="field field-full"><label>Condition description</label><textarea name="description" defaultValue={condition?.description ?? ""} maxLength={2000} /></div>
      </div>
      <div className="actions" style={{ marginTop: 18 }}><SubmitButton>{condition ? "Save condition" : "Add condition"}</SubmitButton></div>
    </form>
  );
}
