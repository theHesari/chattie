import assert from "node:assert/strict";
import { test } from "node:test";
import { DEPARTMENTS, departmentFor, ROLES } from "./roles.ts";

test("the four roles come in the order employee, manager, HR, admin", () => {
  assert.deepEqual(
    ROLES.map((role) => role.id),
    ["employee", "manager", "hr", "admin"],
  );
});

test("only employees and managers choose a department", () => {
  assert.deepEqual(
    ROLES.filter((role) => role.needsDepartment).map((role) => role.id),
    ["employee", "manager"],
  );
});

test("the departments match the ids the API expects", () => {
  assert.deepEqual(
    DEPARTMENTS.map((department) => [department.id, department.name]),
    [
      [2, "Sales"],
      [3, "Engineering"],
      [4, "Marketing"],
      [6, "Customer Support"],
    ],
  );
});

test("every role has a short, non-empty description", () => {
  for (const role of ROLES) {
    assert.ok(role.blurb.length > 0 && role.blurb.length < 120, role.id);
    assert.ok(role.label.length > 0);
  }
});

test("the descriptions do not promise more than the database lets each role see", () => {
  const hr = ROLES.find((role) => role.id === "hr");
  assert.doesNotMatch(hr.blurb, /customers/i); // HR sees every person's data, but orders only their own
  assert.match(hr.blurb, /own/i);
});

test("a department is only sent for roles that take one", () => {
  assert.equal(departmentFor("employee", 3), 3);
  assert.equal(departmentFor("manager", 2), 2);
  assert.equal(departmentFor("hr", 3), null);
  assert.equal(departmentFor("admin", 3), null);
});

test("an unknown or missing department falls back to null for roles that take one", () => {
  assert.equal(departmentFor("employee", 999), null);
  assert.equal(departmentFor("employee", Number.NaN), null);
});
