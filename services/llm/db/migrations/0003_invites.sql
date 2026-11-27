-- Invite-only sign-up. A code is shown once to whoever issues it; only its SHA-256 hash is stored.
-- Idempotent on purpose: it lives in `public`, outside the company schema that tests recreate.

CREATE TABLE IF NOT EXISTS public.invites (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code_hash  text NOT NULL UNIQUE,
    email      text,                                   -- when set, only this address may use the code
    created_by text NOT NULL DEFAULT 'owner',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    used_by    text
);

-- Spend an invite exactly once. True only for an unused, unexpired code whose email (if any) matches;
-- the single UPDATE makes concurrent attempts safe: one wins, the rest get false.
CREATE OR REPLACE FUNCTION public.redeem_invite(p_code_hash text, p_email text, p_used_by text) RETURNS boolean
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE public.invites
       SET used_at = now(), used_by = p_used_by
     WHERE code_hash = p_code_hash
       AND used_at IS NULL
       AND expires_at > now()
       AND (email IS NULL OR lower(email) = lower(p_email));
    RETURN FOUND;
END $$;
