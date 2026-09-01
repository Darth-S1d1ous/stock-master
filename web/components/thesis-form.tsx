"use client";

import { useActionState } from "react";
import { createThesisAction, updateThesisAction } from "@/app/(console)/theses/actions";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { INITIAL_ACTION_STATE } from "@/lib/errors";
import { thesisStatusLabels } from "@/lib/constants";
import type { InvestmentThesis } from "@/types/domain";

export function ThesisForm({ thesis }: { thesis?: InvestmentThesis }) {
  const [state, action] = useActionState(thesis ? updateThesisAction : createThesisAction, INITIAL_ACTION_STATE);
  return (
    <form action={action} className="card card-body">
      <FormMessage state={state} />
      {thesis ? <><input type="hidden" name="id" value={thesis.id} /><input type="hidden" name="expected_version" value={thesis.version} /><input type="hidden" name="original_status" value={thesis.status} /></> : null}
      <div className="form-grid">
        {!thesis ? <div className="field"><label htmlFor="symbol">Stock symbol</label><input id="symbol" name="symbol" placeholder="AAPL" pattern="[A-Za-z][A-Za-z0-9.-]{0,14}" maxLength={15} required /></div> : null}
        {thesis ? <div className="field"><label htmlFor="status">Thesis status</label><select id="status" name="status" defaultValue={thesis.status}>{Object.entries(thesisStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div> : null}
        <div className={thesis ? "field" : "field field-full"}><label htmlFor="title">Thesis title</label><input id="title" name="title" defaultValue={thesis?.title} maxLength={200} required /></div>
        <div className="field field-full"><label htmlFor="description">Investment rationale</label><textarea id="description" name="description" defaultValue={thesis?.description} maxLength={5000} required /><span className="help">Explain why this company is held or monitored. Material fact changes will be verified deterministically against the conditions below.</span></div>
        {thesis ? <div className="field field-full"><label htmlFor="reason">Status change reason</label><input id="reason" name="reason" maxLength={500} placeholder="Required only when changing status" /></div> : null}
      </div>
      <div className="actions" style={{ marginTop: 20 }}><SubmitButton>{thesis ? "Save changes" : "Create thesis"}</SubmitButton></div>
    </form>
  );
}
