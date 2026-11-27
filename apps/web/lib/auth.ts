import { createHash } from "node:crypto";
import { betterAuth } from "better-auth";
import { APIError } from "better-auth/api";
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

/**
 * Sign-up is by invitation only. Spends the invite in the database (single use, unexpired, and bound
 * to this email when the invite names one). Only the code's SHA-256 hash is ever stored or compared.
 */
async function redeemInvite(code: unknown, email: string): Promise<boolean> {
  if (typeof code !== "string" || code.trim() === "" || code.length > 200) {
    return false;
  }
  const hash = createHash("sha256").update(code.trim()).digest("hex");
  const { rows } = await pool.query(
    "SELECT public.redeem_invite($1, $2, $3) AS ok",
    [hash, email, email],
  );
  return rows[0]?.ok === true;
}

export const auth = betterAuth({
  database: pool,
  trustedOrigins,
  emailAndPassword: { enabled: true },
  databaseHooks: {
    user: {
      create: {
        // Runs for every way an account can be created, so the gate cannot be bypassed by
        // calling the endpoint directly instead of using the form.
        before: async (user, context) => {
          const code =
            context?.headers?.get("x-invite-code") ?? context?.body?.inviteCode;
          if (!(await redeemInvite(code, user.email))) {
            throw new APIError("FORBIDDEN", {
              message:
                "Sign-up is by invitation only. Enter a valid, unused invite code.",
            });
          }
        },
        after: (user) => claimUnownedThreads(user.id),
      },
    },
  },
  plugins: [
    // Signs short-lived JWTs (EdDSA) for the FastAPI service; public keys at /api/auth/jwks.
    jwt(),
    nextCookies(), // must stay last
  ],
});
