import { z } from "zod";

const schema = z.object({
  NEXT_PUBLIC_API_URL: z.url(),
});

// Each NEXT_PUBLIC_ variable must be referenced literally so Next.js can inline it into the browser bundle.
export const env = schema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
});
