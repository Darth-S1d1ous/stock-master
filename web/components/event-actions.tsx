"use client";

import { useActionState } from "react";
import { createFeedbackAction, updateEventStatusAction } from "@/app/(console)/events/actions";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { eventStatusLabels, feedbackOptions } from "@/lib/constants";
import { INITIAL_ACTION_STATE } from "@/lib/errors";
import type { EventStatus } from "@/types/domain";

export function EventStatusForm({ eventId, status }: { eventId: string; status: EventStatus }) {
  const [state, action] = useActionState(updateEventStatusAction, INITIAL_ACTION_STATE);
  return <form action={action}><FormMessage state={state} /><input type="hidden" name="event_id" value={eventId} /><div className="field"><label>Workflow status</label><select name="status" defaultValue={status}>{Object.entries(eventStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><div className="actions" style={{ marginTop: 12 }}><SubmitButton>Update status</SubmitButton></div></form>;
}

export function FeedbackForm({ eventId }: { eventId: string }) {
  const [state, action] = useActionState(createFeedbackAction, INITIAL_ACTION_STATE);
  return <form action={action}><FormMessage state={state} /><input type="hidden" name="event_id" value={eventId} /><div className="field"><label>Feedback category</label><select name="feedback_type" defaultValue="useful">{feedbackOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><div className="field" style={{ marginTop: 12 }}><label>Comment</label><textarea name="comment" maxLength={2000} placeholder="Explain why this event is useful, a false positive, or a duplicate…" /></div><div className="actions" style={{ marginTop: 12 }}><SubmitButton>Record feedback</SubmitButton></div></form>;
}
