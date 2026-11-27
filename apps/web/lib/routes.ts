/** URL of a brand-new thread; the id becomes the LangGraph thread id. */
export const newThreadPath = () => `/chat/${crypto.randomUUID()}`;

export const ONBOARDING_PATH = "/onboarding";
/** Onboarding for someone who already has a character: asks for confirmation before replacing it. */
export const CHANGE_CHARACTER_PATH = "/onboarding?change=1";
export const DASHBOARD_PATH = "/dashboard";
