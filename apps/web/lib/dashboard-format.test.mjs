import assert from "node:assert/strict";
import { test } from "node:test";
import {
  barHeights,
  buildRequest,
  canUndo,
  fieldsFor,
  formatDateRange,
  kindLabel,
  newRequestKey,
  nextAttemptKey,
  REQUEST_KINDS,
  statusTone,
  weekdayLabel,
  workKindLabel,
} from "./dashboard-format.ts";

test("bars are scaled to the chosen maximum, clamped, and in date order", () => {
  const bars = barHeights(
    [
      { day: "2026-12-03", hours: 12, kind: "office" },
      { day: "2026-12-01", hours: 0, kind: "leave" },
      { day: "2026-12-02", hours: 5, kind: "remote" },
    ],
    10,
  );
  assert.deepEqual(
    bars.map((bar) => [bar.day, bar.percent, bar.kind]),
    [
      ["2026-12-01", 0, "leave"],
      ["2026-12-02", 50, "remote"],
      ["2026-12-03", 100, "office"],
    ],
  );
});

test("every bar carries a spoken label with weekday, date, hours and kind", () => {
  const [bar] = barHeights([{ day: "2026-12-07", hours: 8, kind: "office" }]);
  assert.equal(bar.label, "Mon 7 Dec: 8 h, office");
  const [holiday] = barHeights([
    { day: "2026-12-25", hours: 0, kind: "holiday" },
  ]);
  assert.equal(holiday.label, "Fri 25 Dec: holiday");
});

test("no days means no bars, and negative or NaN hours never produce a negative bar", () => {
  assert.deepEqual(barHeights([]), []);
  const [bar] = barHeights([{ day: "2026-12-01", hours: -3, kind: "office" }]);
  assert.equal(bar.percent, 0);
});

test("dates read the way people say them", () => {
  assert.equal(formatDateRange("2026-12-07", "2026-12-07"), "7 Dec");
  assert.equal(formatDateRange("2026-12-07", "2026-12-09"), "7 Dec to 9 Dec");
  assert.equal(
    formatDateRange("2026-12-30", "2027-01-04"),
    "30 Dec 2026 to 4 Jan 2027",
  );
  assert.equal(weekdayLabel("2026-12-07"), "Mon 7 Dec");
});

test("every request and work-day kind has a human label", () => {
  assert.equal(kindLabel("day_off"), "Day off");
  assert.equal(kindLabel("schedule_change"), "Schedule change");
  for (const kind of [
    "day_off",
    "sick_day",
    "remote_day",
    "schedule_change",
    "overtime",
  ]) {
    assert.ok(
      kindLabel(kind).length > 0 && !kindLabel(kind).includes("_"),
      kind,
    );
  }
  for (const kind of ["office", "remote", "leave", "sick", "holiday"]) {
    assert.ok(workKindLabel(kind).length > 0, kind);
  }
});

test("decisions have a tone", () => {
  assert.equal(statusTone("approved"), "good");
  assert.equal(statusTone("rejected"), "bad");
  assert.equal(statusTone("cancelled"), "muted");
});

test("a request can be undone only while approved and not yet started", () => {
  const today = "2026-12-01";
  assert.equal(
    canUndo({ status: "approved", startsOn: "2026-12-02" }, today),
    true,
  );
  assert.equal(
    canUndo({ status: "approved", startsOn: "2026-12-01" }, today),
    false,
  ); // starts today
  assert.equal(
    canUndo({ status: "approved", startsOn: "2026-11-20" }, today),
    false,
  );
  assert.equal(
    canUndo({ status: "rejected", startsOn: "2026-12-09" }, today),
    false,
  );
  assert.equal(
    canUndo({ status: "cancelled", startsOn: "2026-12-09" }, today),
    false,
  );
});

test("each kind asks only for the fields it uses", () => {
  assert.deepEqual(fieldsFor("sick_day"), {
    endDate: true,
    times: false,
    hours: false,
    reason: false,
  });
  assert.deepEqual(fieldsFor("schedule_change"), {
    endDate: true,
    times: true,
    hours: false,
    reason: true,
  });
  assert.deepEqual(fieldsFor("overtime"), {
    endDate: false,
    times: false,
    hours: true,
    reason: true,
  });
  assert.equal(fieldsFor("day_off").reason, true);
});

test("a day-off request is built from the form values, omitting what is empty", () => {
  const request = buildRequest(
    "day_off",
    {
      startsOn: "2026-12-07",
      endsOn: "",
      startTime: "",
      endTime: "",
      hours: "",
      reason: "  Long weekend  ",
    },
    "key-1",
  );
  assert.deepEqual(request, {
    kind: "day_off",
    startsOn: "2026-12-07",
    reason: "Long weekend",
    requestKey: "key-1",
  });
});

test("a range keeps its end date", () => {
  const request = buildRequest(
    "day_off",
    {
      startsOn: "2026-12-07",
      endsOn: "2026-12-09",
      startTime: "",
      endTime: "",
      hours: "",
      reason: "",
    },
    "k",
  );
  assert.equal(request.endsOn, "2026-12-09");
  assert.equal("reason" in request, false);
});

test("a sick day never carries a reason, even if the field still holds text", () => {
  const request = buildRequest(
    "sick_day",
    {
      startsOn: "2026-12-01",
      endsOn: "",
      startTime: "",
      endTime: "",
      hours: "",
      reason: "flu",
    },
    "k",
  );
  assert.equal("reason" in request, false);
});

test("a schedule change carries its times and nothing else that does not apply", () => {
  const request = buildRequest(
    "schedule_change",
    {
      startsOn: "2026-12-07",
      endsOn: "2026-12-11",
      startTime: "08:00",
      endTime: "16:00",
      hours: "3",
      reason: "",
    },
    "k",
  );
  assert.equal(request.startTime, "08:00");
  assert.equal(request.endTime, "16:00");
  assert.equal("hours" in request, false);
});

test("overtime carries its hours as a number and no end date", () => {
  const request = buildRequest(
    "overtime",
    {
      startsOn: "2026-12-07",
      endsOn: "2026-12-09",
      startTime: "08:00",
      endTime: "16:00",
      hours: "2.5",
      reason: "Quarter close",
    },
    "k",
  );
  assert.equal(request.hours, 2.5);
  assert.equal("endsOn" in request, false);
  assert.equal("startTime" in request, false);
});

test("hours that are not a number are left out (the server then explains what is needed)", () => {
  const request = buildRequest(
    "overtime",
    {
      startsOn: "2026-12-07",
      endsOn: "",
      startTime: "",
      endTime: "",
      hours: "abc",
      reason: "",
    },
    "k",
  );
  assert.equal("hours" in request, false);
});

test("request keys are distinct valid UUIDs", () => {
  const a = newRequestKey();
  const b = newRequestKey();
  assert.notEqual(a, b);
  assert.match(
    a,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});

test("the form offers every kind exactly once", () => {
  assert.deepEqual([...REQUEST_KINDS].sort(), [
    "day_off",
    "overtime",
    "remote_day",
    "schedule_change",
    "sick_day",
  ]);
});

test("the attempt key changes only once the server has decided", () => {
  const make = () => "fresh-key";
  assert.equal(nextAttemptKey("current-key", true, make), "fresh-key"); // decided (approved or rejected): next attempt is new
  assert.equal(nextAttemptKey("current-key", false, make), "current-key"); // failed or unanswered: a retry reuses the key
});
