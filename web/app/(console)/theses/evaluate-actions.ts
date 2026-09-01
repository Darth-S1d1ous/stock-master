"use server";

import { revalidatePath } from "next/cache";
import { actionError, type ActionState } from "@/lib/errors";
import { evaluateThesis } from "@/lib/api/theses";
import type { MarketDataSource, PriceAdjustment, ThesisMonitoringResult } from "@/types/domain";

export interface EvaluationState extends ActionState { result?: ThesisMonitoringResult }

export async function evaluateThesisAction(_: EvaluationState, data: FormData): Promise<EvaluationState> {
  const id = String(data.get("thesis_id") ?? "");
  const source = String(data.get("source") ?? "alpha_vantage") as MarketDataSource;
  const adjustment = String(data.get("adjustment") ?? "raw") as PriceAdjustment;
  try {
    const result = await evaluateThesis(id, source, adjustment);
    revalidatePath("/"); revalidatePath("/events"); revalidatePath(`/theses/${id}`);
    return { ok: true, message: `Evaluation complete: ${result.matched_count} conditions matched; ${result.event_count} events generated.`, result };
  } catch (error) { return actionError(error); }
}
