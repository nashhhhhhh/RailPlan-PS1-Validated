const { test, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const output = fs.mkdtempSync(path.join(root, ".ps1-test-"));
execFileSync(
  process.execPath,
  [
    path.join(root, "node_modules/typescript/bin/tsc"),
    "app/ps1-optimisation-data.ts",
    "app/components/ps1/demo-state.ts",
    "--outDir",
    output,
    "--module",
    "commonjs",
    "--target",
    "es2022",
    "--moduleResolution",
    "node",
    "--esModuleInterop",
    "--skipLibCheck",
    "--strict",
  ],
  { cwd: root, stdio: "pipe" },
);
fs.writeFileSync(path.join(output, "package.json"), ' {"type":"commonjs"}');
const d = require(path.join(output, "app/ps1-optimisation-data.js"));
const demo = require(path.join(output, "app/components/ps1/demo-state.js"));
after(() => fs.rmSync(output, { recursive: true, force: true }));
test("demo progression, scenarios and bounded solver presets", () => {
  assert.deepEqual(demo.demoSteps, ["Dataset", "Scenario", "Optimisation", "Validation", "Objective", "Export"]);
  for (const scenario of ["A", "B", "C"]) assert.equal(demo.scenarioDescriptions[scenario].length >= 2, true);
  assert.match(demo.scenarioDescriptions.A.join(" "), /ECLO forbidden/);
  assert.match(demo.scenarioDescriptions.B.join(" "), /planned completion dates/);
  assert.match(demo.scenarioDescriptions.C.join(" "), /Separate Alpha and Beta/);
  for (const preset of Object.values(demo.solverPresets)) assert.equal(d.optionsSchema.safeParse({...d.defaults,...preset}).success, true);
});
test("unknown remains distinct from proven infeasibility", () => {
  assert.equal(demo.solverExplanation("UNKNOWN"), "No schedule was found or disproved within the configured search limit.");
  assert.match(demo.solverExplanation("INFEASIBLE"), /proved/);
  assert.match(demo.solverExplanation("VALIDATOR_REJECTED"), /rejected/);
});
test("publication gate requires every validated condition", () => {
  const good = {candidate:true,feasible:true,physicalComplete:true,hardViolations:0,backendAccepted:true};
  assert.equal(demo.publicationGate(good).eligible, true);
  for (const key of ["candidate","feasible","physicalComplete","backendAccepted"]) {
    const result = demo.publicationGate({...good,[key]:false});
    assert.equal(result.eligible, false);
    assert.ok(result.reason.length > 0);
  }
  assert.match(demo.publicationGate({...good,hardViolations:2}).reason, /2 hard violation/);
});
const access = (i) => ({
  activity_id: `A${i}`,
  access_seq: 1,
  week: 1,
  physical_night: 1,
  access_night: 1,
  locked: false,
  eclo: false,
  baseline_week: null,
  baseline_physical_night: null,
});
test("all 421 access rows load across three API pages", async () => {
  const rows = Array.from({ length: 421 }, (_, i) => access(i));
  const calls = [];
  const actual = await d.allPages(
    async (offset) => {
      calls.push(offset);
      return {
        items: rows.slice(offset, offset + 200),
        limit: 200,
        total: rows.length,
        offset,
      };
    },
    d.accessSchema,
    d.accessKey,
  );
  assert.deepEqual(calls, [0, 200, 400]);
  assert.equal(actual.length, 421);
});
test("occupancy pagination preserves distinct location-scoped co-share groups", async () => {
  const rows = Array.from({ length: 205 }, (_, i) => ({
    activity_id: "A",
    week: 1,
    location_id: `L${i}`,
    co_share_group: "G1",
  }));
  const actual = await d.allPages(
    async (offset) => ({
      items: rows.slice(offset, offset + 200),
      total: 205,
      limit: 200,
      offset,
    }),
    d.occupancySchema,
    d.occupancyKey,
  );
  assert.equal(actual.length, 205);
});
test("empty premature page rejects partial schedule", async () => {
  await assert.rejects(
    d.allPages(
      async () => ({ items: [], limit: 200, total: 20, offset: 0 }),
      d.accessSchema,
      d.accessKey,
    ),
    /incomplete page/,
  );
});
test("repeating pages reject rather than looping", async () => {
  await assert.rejects(
    d.allPages(
      async (offset) => ({ items: [access(1)], limit: 1, total: 10, offset }),
      d.accessSchema,
      d.accessKey,
    ),
    /incomplete page/,
  );
});
test("aborted pagination never returns stale data", async () => {
  const c = new AbortController();
  await assert.rejects(
    d.allPages(
      async () => {
        c.abort();
        return { items: [access(1)], total: 1, limit: 200, offset: 0 };
      },
      d.accessSchema,
      d.accessKey,
      c.signal,
    ),
    { name: "AbortError" },
  );
});
test("invalid rows reject at boundary", async () => {
  await assert.rejects(
    d.allPages(
      async () => ({
        items: [{ activity_id: "A" }],
        total: 1,
        limit: 200,
        offset: 0,
      }),
      d.accessSchema,
      d.accessKey,
    ),
  );
});
test("new attempts have distinct keys and immutable input snapshots", () => {
  const values = {
    ...d.defaults,
    locked_placements: [
      { activity_id: "A", access_seq: 1, week: 1, physical_night: 2 },
    ],
    baseline_run_id: "baseline",
  };
  const a = d.newAttempt("instance", values, () => "key-1"),
    b = d.newAttempt("instance", values, () => "key-2");
  values.locked_placements[0].week = 5;
  assert.equal(a.body.locked_placements[0].week, 1);
  assert.notEqual(a.body.idempotency_key, b.body.idempotency_key);
  assert.equal(a.body.baseline_run_id, "baseline");
  assert.equal(a.body.baseline_placements, undefined);
});
test("placement adapter includes only supported Placement fields", () => {
  assert.deepEqual(d.placement(access(1)), {
    activity_id: "A1",
    access_seq: 1,
    week: 1,
    physical_night: 1,
    access_night: 1,
    eclo: 0,
  });
});
test("occupancy joins on activity and week, never local night or group", () => {
  const rows = [
    { activity_id: "A1", week: 1, location_id: "L1", co_share_group: "G1" },
    { activity_id: "A2", week: 1, location_id: "L2", co_share_group: "G1" },
  ];
  const joined = d.joinOccupancy(rows, [
    access(1),
    { ...access(2), physical_night: 3 },
  ]);
  assert.deepEqual(
    joined.map((r) => r.physical_nights),
    [[1], [3]],
  );
});
test("baseline moves distinguish weeks, nights and unchanged assignments", () => {
  assert.equal(d.movement(access(1)), "No baseline");
  assert.equal(
    d.movement({ ...access(1), baseline_week: 2, baseline_physical_night: 1 }),
    "Moved week",
  );
  assert.equal(
    d.movement({ ...access(1), baseline_week: 1, baseline_physical_night: 3 }),
    "Moved night",
  );
  assert.equal(
    d.movement({ ...access(1), baseline_week: 1, baseline_physical_night: 1 }),
    "Unchanged",
  );
});
test("bounded unknown is not reported as infeasible or optimal", () => {
  assert.equal(
    d.statusLabel("UNKNOWN"),
    "No schedule found within the configured limits",
  );
  assert.notEqual(d.statusLabel("FEASIBLE"), d.statusLabel("OPTIMAL"));
});
test("unsupported configuration limits fail before submission", () => {
  for (const options of [
    { ...d.defaults, time_limit_seconds: 0 },
    { ...d.defaults, physical_nights_per_week: 8 },
    { ...d.defaults, random_seed: -1 },
    { ...d.defaults, deterministic_time_limit: 61 },
  ])
    assert.equal(d.optionsSchema.safeParse(options).success, false);
});
test("CSV bytes preserve quotes, CRLF, Unicode and trailing newline", async () => {
  const csv = 'activity_id,description\r\nA1,"α,β"\r\n';
  assert.equal(await d.csvBlob(csv).text(), csv);
  assert.deepEqual(
    Buffer.from(await d.csvBlob(csv).arrayBuffer()),
    Buffer.from(csv),
  );
});
test("connection rejects credentials, queries and unsupported schemes", () => {
  for (const url of [
    "ftp://localhost",
    "http://user:pass@localhost",
    "http://localhost?secret=x",
    "http://localhost#x",
  ])
    assert.throws(() => d.connectionClient(url, "user"));
});
test("official verification claims rejected by artifact schema", () => {
  assert.equal(
    d.artifactsSchema.safeParse({
      run_id: "run",
      files: {},
      physical_validation_complete: true,
      judge_validation: "passed",
      score_verification: "official",
    }).success,
    false,
  );
});

test("browser connection adapter retains the global fetch receiver", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async function () {
    assert.equal(this, globalThis);
    return new Response(
      JSON.stringify({ items: [], total: 0, offset: 0, limit: 50 }),
      { status: 200 },
    );
  };
  try {
    const result = await d
      .connectionClient("http://localhost:8000", "planner")
      .ps1Optimisations("instance");
    assert.equal(result.total, 0);
  } finally {
    globalThis.fetch = original;
  }
});
