import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";
import { serverEnv, trustedOrigins } from "@/lib/env.server";

// search_path=auth (see AUTH_DATABASE_URL): Better Auth's tables live in the "auth" schema.
const pool = new Pool({ connectionString: serverEnv.AUTH_DATABASE_URL });

/**
 * Chats created before sign-in existed have no owner. The very first account
 * claims them (a one-time migration; later accounts find nothing to claim).
 */
async function claimUnownedThreads(userId: string) {
  try {
    await pool.query(
      `UPDATE public.chat_threads SET user_id = $1
       WHERE user_id IS NULL AND (SELECT count(*) FROM "user") = 1`,
      [userId],
    );
  } catch (error) {
    // 42P01: the API hasn't created chat_threads yet, so there's nothing to claim.
    if ((error as { code?: string }).code !== "42P01") throw error;
  }
}

export const auth = betterAuth({
  database: pool,
  trustedOrigins,
  emailAndPassword: { enabled: true },
  databaseHooks: {
    user: { create: { after: (user) => claimUnownedThreads(user.id) } },
  },
  plugins: [
    // Signs short-lived JWTs (EdDSA) for the FastAPI service; public keys at /api/auth/jwks.
    jwt(),
    nextCookies(), // must stay last
  ],
});
