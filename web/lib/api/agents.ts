import "server-only"; // Does NOT bundle into the client
import { apiRequest, queryString } from "@/lib/api/client";
import { ApiError } from "@/lib/errors";
import type { AgentMessage, AgentSession, AgentTurnResult } from "@/types/domain";

const AGENT_TURN_TIMEOUT_MS = 180_000;

// return a Promise that resolves to the new AgentSession
export function createAgentSession(thesisId: string) {
    return apiRequest<AgentSession>(
        `/api/v1/theses/${encodeURIComponent(thesisId)}/agent/sessions`,
        {method: "POST"},
    );
}

export async function getOpenAgentSession(thesisId: string): Promise<AgentSession | null> {
    try{
        return await apiRequest<AgentSession>(
            `/api/v1/theses/${encodeURIComponent(thesisId)}/agent/sessions/open`,
        );
    } catch (error) {
        if (error instanceof ApiError && error.status === 404 && error.code === "agent_session_not_found") {
            return null;
        }
        throw error;
    }
}

export function listAgentMessages(sessionId: string, filters: { limit?: number; offset?: number } = {}) {
    return apiRequest<AgentMessage[]>(
        `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/messages${queryString(filters)}`,
    )
}

export function generateAgentTurn(sessionId: string) {
    return apiRequest<AgentTurnResult>(
        `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/generate`,
        {method: "POST", timeoutMs: AGENT_TURN_TIMEOUT_MS},
    )
}

export function chatWithAgent(sessionId: string, message: string) {
    return apiRequest<AgentTurnResult>(
        `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/chat`,
        {
            method: "POST", 
            timeoutMs: AGENT_TURN_TIMEOUT_MS,
            body: JSON.stringify({message}),
        },
    )
}

export function closeAgentSession(sessionId: string) {
    return apiRequest<AgentSession>(
        `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/close`,
        {method: "POST"},
    )
}