import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  characterSchema,
  historySchema,
  meSchema,
  requestsSchema,
  resultSchema,
  teamSchema,
} from "./schemas.ts";

// Recorded from the real API by services/llm/tests/test_contract_fixtures.py.
const fixture = (name) =>
  JSON.parse(
    readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"),
  );

test("the API's character parses", () => {
  const character = characterSchema.parse(fixture("character"));
  assert.equal(character.role, "manager");
  assert.equal(character.department, "Sales");
});

test("/me may be null (no character yet) or a character", () => {
  assert.equal(meSchema.parse(null), null);
  assert.equal(meSchema.parse(fixture("character")).name, "Ada Lovelace");
});

test("the history parses and keeps its balance arithmetic", () => {
  const history = historySchema.parse(fixture("history"));
  assert.equal(
    history.balance.remaining,
    history.balance.allowance - history.balance.used,
  );
  assert.ok(history.events.some((event) => event.kind === "hired"));
  assert.ok(history.recentWorkDays.length > 0);
});

test("a history without a balance is rejected", () => {
  const { balance: _removed, ...incomplete } = fixture("history");
  assert.throws(() => historySchema.parse(incomplete));
});

test("requests parse, including nullable times and reasons", () => {
  const requests = requestsSchema.parse(fixture("requests"));
  assert.ok(requests.length > 0);
  assert.ok(
    requests.every((request) => typeof request.decisionReason === "string"),
  );
});

test("a request with an unknown status is rejected", () => {
  const [first, ...rest] = fixture("requests");
  assert.throws(() =>
    requestsSchema.parse([{ ...first, status: "pending" }, ...rest]),
  );
});

test("a decision parses whether it was approved or cancelled", () => {
  assert.equal(resultSchema.parse(fixture("result")).status, "approved");
  assert.equal(resultSchema.parse(fixture("cancelled")).status, "cancelled");
});

test("a malformed request (no id) is a valid, rejected decision", () => {
  const result = resultSchema.parse({
    id: null,
    status: "rejected",
    decisionReason: "Rejected: it can't start in the past",
    balanceAfter: null,
  });
  assert.equal(result.id, null);
});

test("the team parses", () => {
  const team = teamSchema.parse(fixture("team"));
  assert.ok(team.length >= 3 && team.length <= 5);
  assert.ok(team.every((member) => member.name.length > 0));
});
