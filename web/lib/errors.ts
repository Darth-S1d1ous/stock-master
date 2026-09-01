export interface ErrorEnvelope {
  code: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ActionState {
  ok: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
}

export const INITIAL_ACTION_STATE: ActionState = { ok: false };

export function actionError(error: unknown): ActionState {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return { ok: false, message: "Data modified, please refresh and try again" };
    }
    return { ok: false, message: error.message };
  }
  return { ok: false, message: "The operation was not completed. Please try again later." };
}
