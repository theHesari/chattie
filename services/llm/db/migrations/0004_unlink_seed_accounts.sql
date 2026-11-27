-- Seed staff are shared world data. Before generated characters existed, `make company-link` tied app
-- accounts to them; under the character model an account owns a generated employee instead. Unlink any
-- such account so it goes through character creation on its next visit. Only the link is removed;
-- chats and the account itself are untouched.
UPDATE company.employees SET user_id = NULL WHERE origin = 'seed' AND user_id IS NOT NULL;
