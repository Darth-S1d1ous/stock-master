"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { actionError, type ActionState } from "@/lib/errors";
import { createCondition, createThesis, updateCondition, updateThesis } from "@/lib/api/theses";
import type { ConditionKind, ComparisonOperator, MetricCode, ThesisStatus } from "@/types/domain";

const text = (data: FormData, key: string) => String(data.get(key) ?? "").trim();

export async function createThesisAction(_: ActionState, data: FormData): Promise<ActionState> {
  const symbol = text(data, "symbol").toUpperCase();
  const title = text(data, "title");
  const description = text(data, "description");
  if (!/^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol)) return { ok: false, message: "Enter a valid U.S. equity symbol." };
  if (!title || !description) return { ok: false, message: "The title and investment rationale are required." };
  let id: string;
  try {
    id = (await createThesis({ symbol, title, description })).id;
  } catch (error) { return actionError(error); }
  revalidatePath("/");
  revalidatePath("/theses");
  redirect(`/theses/${id}`);
}

export async function updateThesisAction(_: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "id");
  const title = text(data, "title");
  const description = text(data, "description");
  const expectedVersion = Number(text(data, "expected_version"));
  const status = text(data, "status") as ThesisStatus;
  const originalStatus = text(data, "original_status") as ThesisStatus;
  const reason = text(data, "reason");
  if (!id || !title || !description || !Number.isInteger(expectedVersion)) return { ok: false, message: "Check the required fields." };
  if (status !== originalStatus && !reason) return { ok: false, message: "A reason is required when changing thesis status." };
  const statusChange = status !== originalStatus ? { status, reason } : {};
  try {
    await updateThesis(id, { expected_version: expectedVersion, title, description, ...statusChange });
    revalidatePath("/"); revalidatePath("/theses"); revalidatePath(`/theses/${id}`);
    return { ok: true, message: "Investment thesis updated." };
  } catch (error) { return actionError(error); }
}

export async function archiveThesisAction(data: FormData): Promise<void> {
  const id = text(data, "id");
  const expectedVersion = Number(text(data, "expected_version"));
  if (!id || !Number.isInteger(expectedVersion)) return;
  try {
    await updateThesis(id, { expected_version: expectedVersion, status: "archived", reason: "Archived from the web console." });
    revalidatePath("/"); revalidatePath("/theses"); revalidatePath(`/theses/${id}`);
  } catch (error) {
    console.error(JSON.stringify({ err_code: "archive_thesis_failed", err_msg: error instanceof Error ? error.message : "Unknown error" }));
  }
}

export async function createConditionAction(_: ActionState, data: FormData): Promise<ActionState> {
  const thesisId = text(data, "thesis_id");
  const name = text(data, "name");
  const threshold = text(data, "threshold");
  if (!thesisId || !name || !threshold || !Number.isFinite(Number(threshold))) return { ok: false, message: "Enter a valid condition name and threshold." };
  try {
    await createCondition(thesisId, {
      name,
      description: text(data, "description") || null,
      kind: text(data, "kind") as ConditionKind,
      metric: text(data, "metric") as MetricCode,
      operator: text(data, "operator") as ComparisonOperator,
      threshold,
      consecutive_periods: Number(text(data, "consecutive_periods") || "1"),
      enabled: data.get("enabled") === "on",
    });
    revalidatePath(`/theses/${thesisId}`);
    return { ok: true, message: "Monitoring condition added." };
  } catch (error) { return actionError(error); }
}

export async function updateConditionAction(_: ActionState, data: FormData): Promise<ActionState> {
  const thesisId = text(data, "thesis_id");
  const conditionId = text(data, "condition_id");
  const threshold = text(data, "threshold");
  try {
    await updateCondition(thesisId, conditionId, {
      expected_version: Number(text(data, "expected_version")),
      name: text(data, "name"), description: text(data, "description") || null,
      kind: text(data, "kind"), metric: text(data, "metric"), operator: text(data, "operator"),
      threshold, consecutive_periods: Number(text(data, "consecutive_periods")), enabled: data.get("enabled") === "on",
    });
    revalidatePath(`/theses/${thesisId}`);
    return { ok: true, message: "Monitoring condition updated." };
  } catch (error) { return actionError(error); }
}
