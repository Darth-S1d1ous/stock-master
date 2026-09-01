"use server";

import { revalidatePath } from "next/cache";
import { actionError, type ActionState } from "@/lib/errors";
import { createEventFeedback, updateEventStatus } from "@/lib/api/events";
import type { EventStatus, FeedbackType } from "@/types/domain";

export async function updateEventStatusAction(_: ActionState, data: FormData): Promise<ActionState> {
  const id = String(data.get("event_id") ?? "");
  const status = String(data.get("status") ?? "") as EventStatus;
  try {
    await updateEventStatus(id, status);
    revalidatePath("/"); revalidatePath("/events"); revalidatePath(`/events/${id}`);
    return { ok: true, message: "Event status updated." };
  } catch (error) { return actionError(error); }
}

export async function createFeedbackAction(_: ActionState, data: FormData): Promise<ActionState> {
  const id = String(data.get("event_id") ?? "");
  const type = String(data.get("feedback_type") ?? "") as FeedbackType;
  const comment = String(data.get("comment") ?? "").trim();
  try {
    await createEventFeedback(id, type, comment);
    revalidatePath(`/events/${id}`);
    return { ok: true, message: "Feedback recorded. Existing history was preserved." };
  } catch (error) { return actionError(error); }
}
