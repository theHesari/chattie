/**
 * Query key for the signed-in user's thread list. Shared by the server (which seeds
 * the cache) and the browser (which refetches it), so it must not import server-only
 * or browser-only code.
 */
export const threadsKey = ["threads"] as const;
