import { z } from "zod";

/** Server-only configuration. None of these may be exposed to the browser. */
export const serverEnv = z
  .object({
    BETTER_AUTH_SECRET: z.string().min(32),
    BETTER_AUTH_URL: z.url(),
    AUTH_TRUSTED_ORIGINS: z.string().default(""),
    AUTH_DATABASE_URL: z.string().startsWith("postgres"),
  })
  .parse(process.env);

export const trustedOrigins = serverEnv.AUTH_TRUSTED_ORIGINS.split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);
