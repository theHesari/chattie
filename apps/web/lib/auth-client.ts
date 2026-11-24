import { jwtClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

// No baseURL: the client talks to whichever origin the app is open on (localhost or 127.0.0.1).
export const authClient = createAuthClient({ plugins: [jwtClient()] });
