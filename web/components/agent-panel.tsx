"use client";

import { useActionState } from "react";
import {
    chatWithAgentAction,
    closeAgentSessionAction,
    generateAgentTurnAction,
    startAgentSessionAction,
    type AgentTurnState,
} from "@/app/(console)/theses/agent-actions";
import { FormMessage } from "@/components/form-message";
import {SubmitButton} from "@/components/submit-button";
import {INITIAL_ACTION_STATE, type ActionState} from "@/lib/errors";
import {formatDateTime} from "@/lib/format";
import type {AgentMessage, AgentSession} from "@/types/domain";

const initialTurnState: AgentTurnState = { ok: false };
const GENERATE_PROMPT_PREFIX = "Create deterministic monitoring conditions for the current thesis.";

export function AgentPanel(
    {thesisId, session, messages}: {thesisId: string; session: AgentSession | null; messages: AgentMessage[]}
) {
    // e.g. startAction wraps startAgentSessionAction. They are different. startAction extract prevState, take FormData, call setState
    const [startState, startAction] = useActionState(startAgentSessionAction, INITIAL_ACTION_STATE);
    const [generateState, generateAction] = useActionState(generateAgentTurnAction, initialTurnState);
    const [chatState, chatAction] = useActionState(chatWithAgentAction, initialTurnState);
    const [closeState, closeAction] = useActionState(closeAgentSessionAction, INITIAL_ACTION_STATE);

    return (
        <div className="card">
            <div className="card-header">
            <div>
                <p className="eyebrow">Condition author</p>
                <h2>Draft conditions with AI</h2>
            </div>
            <span className="badge">{session ? "Session open" : "No session"}</span>
            </div>
            <div className="card-body">
            {session ? (
                <OpenSession
                thesisId={thesisId}
                session={session}
                messages={messages}
                generateState={generateState}
                generateAction={generateAction}
                chatState={chatState}
                chatAction={chatAction}
                closeState={closeState}
                closeAction={closeAction}
                />
            ) : (
                <>
                <FormMessage state={startState} />
                <p className="lede">
                    Start a session to generate monitoring conditions from this thesis,
                    or describe the rule you want in chat. The agent can only use the
                    metric catalog; it cannot evaluate or ingest market data.
                </p>
                <form action={startAction} style={{ marginTop: 18 }}>
                    <input type="hidden" name="thesis_id" value={thesisId} />
                    <SubmitButton pendingText="Starting…">Start agent session</SubmitButton>
                </form>
                </>
            )}
            </div>
        </div>
    );
}

function OpenSession({
    thesisId,
    session,
    messages,
    generateState,
    generateAction,
    chatState,
    chatAction,
    closeState,
    closeAction,
}: {
    thesisId: string;
    session: AgentSession;
    messages: AgentMessage[];
    generateState: AgentTurnState;
    generateAction: (payload: FormData) => void;
    chatState: AgentTurnState;
    chatAction: (payload: FormData) => void;
    closeState: ActionState;
    closeAction: (payload: FormData) => void;
}) {
    const visible = messages.filter((message) => message.role !== "system");

    return (
        <>
      <p className="subtle">Started {formatDateTime(session.created_at)}</p>
      <div style={{ marginTop: 18 }}>
        {visible.length ? visible.map((message) => (
          <MessageItem key={message.id} message={message} />
        )) : (
          <p className="lede">No messages yet. Generate conditions or send a chat message.</p>
        )}
      </div>
      <FormMessage state={generateState} />
      <form action={generateAction} style={{ marginTop: 18 }}>
        <input type="hidden" name="thesis_id" value={thesisId} />
        <input type="hidden" name="session_id" value={session.id} />
        <SubmitButton pendingText="Drafting…">Generate conditions</SubmitButton>
      </form>
      <FormMessage state={chatState} />
      <form action={chatAction} style={{ marginTop: 18 }}>
        <input type="hidden" name="thesis_id" value={thesisId} />
        <input type="hidden" name="session_id" value={session.id} />
        <div className="field">
          <label>Message</label>
          <textarea
            name="message"
            key={messages.length}
            maxLength={20000}
            required
            placeholder="Add a risk rule for a 5% daily drop."
          />
        </div>
        <div className="actions" style={{ marginTop: 18 }}>
          <SubmitButton pendingText="Sending…">Send</SubmitButton>
        </div>
      </form>
      <FormMessage state={closeState} />
      <form action={closeAction} style={{ marginTop: 22 }}>
        <input type="hidden" name="thesis_id" value={thesisId} />
        <input type="hidden" name="session_id" value={session.id} />
        <SubmitButton className="button button-danger" pendingText="Closing…">
          Close session
        </SubmitButton>
      </form>
    </>
    );
}

function MessageItem({ message }: { message: AgentMessage }) {
    return (
        <div className="condition">
      <div className="condition-top">
        <div>
          <strong>{roleLabel(message)}</strong>
          <p className="subtle" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
            {messageBody(message)}
          </p>
        </div>
        <span className="badge">{message.role}</span>
      </div>
    </div>
    );
}

function roleLabel(message: AgentMessage): string {
    if (message.role === 'tool') return message.tool_name ?? "Tool";
    if (message.role === 'assistant') return "Agent";
    return "You";
}

function messageBody(message: AgentMessage): string {
    if (message.role === 'tool') {
        return message.tool_name
            ? `Ran ${message.tool_name}.`
            : "Ran a tool.";
    }
    if (message.role === 'user' && message.content.startsWith(GENERATE_PROMPT_PREFIX)) {
        return "Requested condition generation.";
    }
    return message.content;
}