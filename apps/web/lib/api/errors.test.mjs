import assert from "node:assert/strict";
import { test } from "node:test";
import { describeApiError } from "./errors.ts";

test("too many requests tells the user how long to wait", () => {
  assert.match(describeApiError(429, { detail: "x" }, "120"), /120 seconds/);
  assert.match(describeApiError(429, null), /wait/i);
});

test("a validation message from the server is shown as is", () => {
  assert.equal(
    describeApiError(422, {
      detail: "Rejected: the end date is before the start date",
    }),
    "Rejected: the end date is before the start date",
  );
});

test("a list of validation errors shows the first message", () => {
  const body = {
    detail: [
      {
        loc: ["body", "displayName"],
        msg: "Value error, a display name is required",
        type: "value_error",
      },
    ],
  };
  assert.equal(
    describeApiError(422, body),
    "Value error, a display name is required",
  );
});

test("409 tells apart 'no character yet' from 'your character changed'", () => {
  assert.match(
    describeApiError(409, {
      detail: "you have no character yet: create one first (POST /character)",
    }),
    /create one/i,
  );
  assert.match(
    describeApiError(409, {
      detail:
        "your character changed while this was running: reload and try again",
    }),
    /reload/i,
  );
  assert.match(
    describeApiError(409, {
      detail: "the platform is at its limit of 500 active characters",
    }),
    /limit/i,
  );
});

test("a server that is not set up, an expired session and a server fault each get plain words", () => {
  assert.match(describeApiError(503, null), /isn't set up/i);
  assert.match(describeApiError(401, null), /sign in/i);
  assert.match(describeApiError(500, null), /our side/i);
});

test("nothing ever shows raw JSON or a stack trace", () => {
  for (const status of [400, 404, 418, 422, 500]) {
    const text = describeApiError(status, { weird: { nested: [1, 2, 3] } });
    assert.doesNotMatch(text, /[{}[\]]|Traceback|undefined|\[object/);
  }
});
