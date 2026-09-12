// Next SWC/Turbopack/webpack scans this declaration
"use server"; // the async functions exported from this file are executed on the server

import { revalidatePath } from "next/cache";
import {
    chatWithAgent,
    closeAgentSession,
    createAgentSession,
    generateAgentTurn,
} from "@/lib/api/agents";
import {actionError, ApiError, type ActionState} from "@/lib/errors";
import type { AgentTurnResult } from "@/types/domain";

const text = (data: FormData, key: string) => String(data.get(key) ?? "").trim();

export interface AgentTurnState extends ActionState {
    result?: AgentTurnResult;
}

export async function startAgentSessionAction(_: ActionState, data: FormData): Promise<ActionState> {
    const thesisId = text(data, "thesis_id");
    if (!thesisId) return {ok: false, message: "Thesis ID is required"};
    
    try {
        await createAgentSession(thesisId);
        revalidatePath(`/theses/${thesisId}`);
        return {ok: true, message: "Agent session started."};
    } catch (error) {
        return agentActionError(error, thesisId);
    }
}

export async function generateAgentTurnAction(
    _: AgentTurnState,
    data: FormData,
): Promise<AgentTurnState> {
    const thesisId = text(data, "thesis_id");
    const sessionId = text(data, "session_id");
    if (!thesisId || !sessionId) return { ok: false, message: "Session is required." };
    try {
        const result = await generateAgentTurn(sessionId);
        revalidatePath(`/theses/${thesisId}`);
        return {
        ok: true,
        message: result.stop_reason === "max_rounds"
            ? "The agent stopped after the maximum number of tool rounds."
            : "Conditions drafted.",
        result,
        };
    } catch (error) {
        return agentActionError(error, thesisId);
    }
}

export async function chatWithAgentAction(
  _: AgentTurnState,
  data: FormData,
): Promise<AgentTurnState> {
    const thesisId = text(data, "thesis_id");
    const sessionId = text(data, "session_id");
    const message = text(data, "message");
    if (!thesisId || !sessionId) return { ok: false, message: "Session is required." };
    if (!message) return { ok: false, message: "Enter a message." };
    if (message.length > 20000) return { ok: false, message: "Message is too long." };
    try {
        const result = await chatWithAgent(sessionId, message);
        revalidatePath(`/theses/${thesisId}`);
        return { ok: true, message: "Reply received.", result };
    } catch (error) {
        return agentActionError(error, thesisId);
    }
}

export async function closeAgentSessionAction(
    _: ActionState,
    data: FormData,
): Promise<ActionState> {
    const thesisId = text(data, "thesis_id");
    const sessionId = text(data, "session_id");
    if (!thesisId || !sessionId) return { ok: false, message: "Session is required." };
    try {
        await closeAgentSession(sessionId);
        revalidatePath(`/theses/${thesisId}`);
        return { ok: true, message: "Agent session closed." };
    } catch (error) {
        return agentActionError(error, thesisId);
    }
}

function agentActionError(error: unknown, thesisId?: string): ActionState {
    if (error instanceof ApiError) {
        if (error.code === "agent_session_closed") {
            return { ok: false, message: "This agent session is closed. Start a new session." };
        }
        if (error.code === "agent_session_conflict") {
            if (thesisId) revalidatePath(`/theses/${thesisId}`);
            return { ok: false, message: "An open agent session already exists for this thesis." };
        }
    }
    return actionError(error);
}