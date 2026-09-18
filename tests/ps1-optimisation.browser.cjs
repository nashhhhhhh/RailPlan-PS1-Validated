// Run with the dev server on http://127.0.0.1:3011 and Playwright available.
// Uses explicit mocked API responses; screenshots are not live PostgreSQL evidence.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(
  process.env.RAILPLAN_PLAYWRIGHT_MODULE || "playwright",
);
const base = process.env.RAILPLAN_UI_URL || "http://127.0.0.1:3011";
const iid = "11111111-1111-4111-8111-111111111111",
  rid = "22222222-2222-4222-8222-222222222222",
  failed = "33333333-3333-4333-8333-333333333333";
const bundle = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../public/ps1/example.json"), "utf8"),
);
const aid = bundle.dataset.tables.activity_details[0].activity_id,
  loc = bundle.dataset.tables.location_supply[0].location_id,
  contract = bundle.dataset.tables.activity_details[0].contract_number;
const accepted = {
  id: rid,
  instance_id: iid,
  baseline_run_id: null,
  solver_status: "FEASIBLE",
  terminal_outcome: "feasible",
  publishable: true,
  physical_validation_complete: true,
  primary_optimal: false,
  lexicographic_complete: false,
  objective_score: "48.30",
  primary_objective_bound: "40.00",
  primary_objective_gap: "0.171842650104",
  solve_duration_seconds: 12.3,
  created_at: "2026-09-18T12:00:00Z",
};
const rejected = {
  ...accepted,
  id: failed,
  solver_status: "UNKNOWN",
  terminal_outcome: "bounded",
  publishable: false,
  physical_validation_complete: false,
  objective_score: null,
  primary_objective_bound: null,
  primary_objective_gap: null,
};
const accesses = Array.from({ length: 205 }, (_, i) => ({
  activity_id: i === 0 ? aid : `BROWSER-${i}`,
  access_seq: 1,
  week: 1 + Math.floor(i / 7),
  physical_night: 1 + (i % 7),
  access_night: 1,
  locked: false,
  eclo: false,
  baseline_week: i === 0 ? 2 : null,
  baseline_physical_night: i === 0 ? 2 : null,
}));
const occupancies = accesses.map((a, i) => ({
  activity_id: a.activity_id,
  week: a.week,
  location_id: i === 0 ? loc : `TEST:${i}`,
  co_share_group: "1",
}));
function detail(run) {
  return {
    run,
    result: {
      solver_status: run.solver_status,
      publishable: run.publishable,
      primary_optimal: false,
      lexicographic_complete: false,
      solve_time_seconds: 12.3,
      physical_validation_complete: run.physical_validation_complete,
      settings: { physical_nights_per_week: 7 },
      objective_components: run.publishable
        ? {
            nights_scheduled: 205,
            contracts_overrunning: 1,
            overrun_days_total: 7,
            priority_weighted_overrun: "48.30",
          }
        : null,
      completion_changes: [],
      stages: [],
      judge_validation: "not_run",
      score_verification: "internal_only",
    },
    validation: run.publishable
      ? {
          validator_version: "ps1-validator/1.1.0",
          validation_status: "feasible",
          hard_violations: [],
          warnings: [],
        }
      : null,
    diagnostics: run.publishable
      ? []
      : [
          {
            code: "time_limit",
            message: "No incumbent within the configured limits.",
          },
        ],
    contract_results: run.publishable
      ? [
          {
            contract_number: contract,
            simulated_completion_date: "2026-12-31",
            overrun_days: 7,
            weighted_overrun: "48.30",
          },
        ]
      : [],
  };
}
const csv = 'activity_id,note\r\nA1,"α,β"\r\n';
const screenshots = path.join(__dirname, "../docs/ui-screenshots");
fs.mkdirSync(screenshots, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    reducedMotion: "reduce",
    acceptDownloads: true,
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => console.log("PAGE ERROR", e.message));
  page.on("requestfailed", (r) =>
    console.log("REQUEST FAILED", r.url(), r.failure()?.errorText),
  );
  let checks = 0;
  const posts = [],
    pageCalls = [];
  let delayPost = false,
    failNext = false,
    artifactConflict = false,
    keyConflict = false,
    holdDetail = false;
  let releasePost, releaseDetail;
  const check = (name) => {
    checks++;
    console.log(`PASS ${checks}: ${name}`);
  };
  async function fulfill(route, data, status = 200) {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
      headers: { "Access-Control-Allow-Origin": "*" },
    });
  }
  await page.route("**/api/ps1/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      p = url.pathname;
    if (req.method() === "OPTIONS")
      return route.fulfill({
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "Content-Type,X-Demo-User-Id",
          "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
      });
    if (p.endsWith("/optimise/scenario-a")) {
      posts.push({ body: req.postDataJSON(), headers: req.headers() });
      if (failNext) {
        failNext = false;
        return route.abort("failed");
      }
      if (keyConflict) {
        keyConflict = false;
        return fulfill(
          route,
          {
            error: {
              code: "CONFLICT",
              message: "Idempotency key already used with different inputs",
              fields: [],
              correlation_id: "test-key",
            },
          },
          409,
        );
      }
      if (delayPost) await new Promise((r) => (releasePost = r));
      return fulfill(route, {
        run_id: rid,
        created: posts.length === 1,
        reused: posts.length > 1,
      });
    }
    if (p === "/api/ps1/instances" && req.method() === "POST")
      return fulfill(route, { id: iid, created: true });
    if (p === "/api/ps1/instances")
      return fulfill(route, { items: [{ id: iid, name: "Browser fixture" }] });
    if (p === `/api/ps1/instances/${iid}`)
      return fulfill(route, {
        id: iid,
        name: "Browser fixture",
        dataset: bundle.dataset,
      });
    if (p.endsWith("/optimisations"))
      return fulfill(route, {
        items: [accepted, rejected],
        total: 2,
        limit: 50,
        offset: 0,
      });
    if (p.endsWith("/artifacts"))
      return artifactConflict
        ? fulfill(
            route,
            {
              error: {
                code: "CONFLICT",
                message: "Run has no internally accepted submission artifacts",
                fields: [],
                correlation_id: "test",
              },
            },
            409,
          )
        : fulfill(route, {
            run_id: rid,
            files: {
              "SCHEDULE_ACCESS.csv": csv,
              "SCHEDULE_OCCUPANCY.csv": csv,
              "RESULTS.csv": csv,
            },
            physical_validation_complete: true,
            judge_validation: "not_run",
            score_verification: "internal_only",
          });
    if (p.endsWith("/accesses") || p.endsWith("/occupancies")) {
      const offset = Number(url.searchParams.get("offset") || 0),
        rows = p.endsWith("/accesses") ? accesses : occupancies;
      pageCalls.push([p, offset]);
      return fulfill(route, {
        items: rows.slice(offset, offset + 200),
        total: rows.length,
        limit: 200,
        offset,
      });
    }
    if (p === `/api/ps1/optimisations/${rid}`) {
      if (holdDetail) await new Promise((r) => (releaseDetail = r));
      return fulfill(route, detail(accepted));
    }
    if (p === `/api/ps1/optimisations/${failed}`)
      return fulfill(route, detail(rejected));
    return fulfill(
      route,
      {
        error: {
          code: "NOT_FOUND",
          message: "Mock route missing",
          fields: [],
          correlation_id: "test",
        },
      },
      404,
    );
  });
  const opt = () => page.locator('[aria-label$="optimisation workspace"]');
  const shot = async (name) => {
    const focus = name.startsWith("01")
      ? opt().locator(".opt-callout")
      : name.startsWith("02")
        ? opt().locator(".opt-solving")
        : name.startsWith("03") || name.startsWith("10")
          ? opt().locator(".opt-result")
          : opt().locator(".opt-panel");
    await focus.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(screenshots, name + ".png"),
      fullPage: false,
    });
  };
  try {
    await page.goto(base, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "PS1 · Hackathon dataset" }).click();
    await page
      .getByRole("button", { name: "Load organiser dataset", exact: true })
      .click();
    await opt().waitFor();
    assert.equal(
      await opt()
        .getByRole("button", { name: "Generate schedule", exact: true })
        .isDisabled(),
      true,
    );
    check("requires a saved instance");
    await shot("01-save-prerequisite");
    await opt().getByRole("button", { name: "Go to Save Dataset" }).click();
    await page
      .getByRole("button", { name: "Save dataset", exact: true })
      .click();
    await opt().locator(".opt-history-item").first().waitFor();
    check("saved history loads independently of legacy capabilities");
    await page.getByRole("button", { name: "Scenario B", exact: true }).click();
    assert.equal(
      await opt()
        .getByRole("button", { name: "Generate schedule", exact: true })
        .isDisabled(),
      false,
    );
    await page.getByRole("button", { name: "Scenario C", exact: true }).click();
    assert.equal(
      await opt()
        .getByRole("button", { name: "Generate schedule", exact: true })
        .isDisabled(),
      true,
    );
    assert.equal(posts.length, 0);
    await page.getByRole("button", { name: "Scenario A", exact: true }).click();
    check("B is enabled, C remains disabled, and neither generates Scenario A requests");
    delayPost = true;
    await opt()
      .getByRole("button", { name: "Generate schedule", exact: true })
      .click();
    await opt().getByText("Searching the night network").waitFor();
    await shot("02-solving");
    while (!releasePost) await page.waitForTimeout(20);
    releasePost();
    delayPost = false;
    await opt()
      .getByRole("heading", { name: "Feasible schedule found", exact: true })
      .waitFor();
    assert.equal(posts[0].body.time_limit_seconds, 20);
    assert.equal(posts[0].body.physical_nights_per_week, 7);
    assert.ok(posts[0].body.idempotency_key);
    assert.ok(posts[0].headers["x-demo-user-id"]);
    check("correct request, key and demo header reach the endpoint");
    assert.equal(
      await opt()
        .getByRole("heading", { name: "Optimal schedule found", exact: true })
        .count(),
      0,
    );
    check("FEASIBLE is not labelled optimal");
    assert.ok(pageCalls.some(([p, o]) => p.endsWith("accesses") && o === 200));
    assert.ok(
      pageCalls.some(([p, o]) => p.endsWith("occupancies") && o === 200),
    );
    check("access and occupancy pagination loads beyond 200");
    await shot("03-result-and-history");
    await opt().getByLabel("Filter week", { exact: true }).fill("1");
    await opt()
      .getByRole("button", { name: new RegExp(`${aid} access 1,`) })
      .click();
    await opt()
      .getByRole("region", { name: "Selected access details" })
      .waitFor();
    assert.ok((await page.locator(".ps1-network .ps1-highlight").count()) > 0);
    check("selecting access highlights real dataset footprint");
    await shot("04-timeline");
    await opt().getByRole("button", { name: "Lock for next run" }).click();
    await opt()
      .getByRole("button", { name: "Use as baseline", exact: true })
      .click();
    await opt()
      .getByRole("button", { name: "Generate schedule", exact: true })
      .click();
    await page.waitForFunction(() =>
      document.querySelector(".opt-notice")?.textContent?.includes("reused"),
    );
    assert.equal(posts[1].body.baseline_run_id, rid);
    assert.equal(posts[1].body.baseline_placements, undefined);
    assert.deepEqual(Object.keys(posts[1].body.locked_placements[0]).sort(), [
      "access_night",
      "access_seq",
      "activity_id",
      "physical_night",
      "week",
    ]);
    assert.notEqual(
      posts[1].body.idempotency_key,
      posts[0].body.idempotency_key,
    );
    check("baseline and supported lock fields sent with a fresh key");
    await opt().getByRole("tab", { name: "Occupancy", exact: true }).click();
    await shot("05-occupancy");
    await opt().getByRole("tab", { name: "Contracts", exact: true }).click();
    await shot("06-contracts");
    await opt().getByRole("tab", { name: "Validation", exact: true }).click();
    await shot("07-validation");
    assert.ok(
      (await opt()
        .getByText(
          "Judge validation: Not run · Score verification: Internal only",
          { exact: true },
        )
        .count()) > 0,
    );
    check("internal verification labels preserved");
    await opt().getByRole("tab", { name: "Downloads", exact: true }).click();
    artifactConflict = true;
    await opt()
      .getByRole("button", { name: "Load saved artifacts", exact: true })
      .click();
    await opt().getByRole("alert").waitFor();
    assert.equal(
      await opt().getByRole("button", { name: "Download all files" }).count(),
      0,
    );
    check("artifact 409 keeps result without broken download buttons");
    artifactConflict = false;
    await opt()
      .getByRole("button", { name: "Load saved artifacts", exact: true })
      .click();
    await opt()
      .getByRole("button", { name: /SCHEDULE_ACCESS.csv/ })
      .waitFor();
    await shot("08-downloads");
    const event = page.waitForEvent("download");
    await opt()
      .getByRole("button", { name: /SCHEDULE_ACCESS.csv/ })
      .click();
    const download = await event;
    assert.equal(fs.readFileSync(await download.path(), "utf8"), csv);
    check("download bytes match exact saved CSV");
    await opt()
      .locator(".opt-history-item")
      .filter({ hasText: "UNKNOWN" })
      .click();
    await opt()
      .getByRole("heading", {
        name: "No schedule found within the configured limits",
        exact: true,
      })
      .waitFor();
    assert.equal(
      await opt()
        .getByRole("button", { name: "Load saved artifacts", exact: true })
        .count(),
      0,
    );
    await opt().getByRole("tab", { name: "Diagnostics", exact: true }).click();
    await shot("09-failed-diagnostics");
    check("UNKNOWN remains inspectable and has no artifacts");
    failNext = true;
    await opt()
      .getByRole("button", { name: "Generate schedule", exact: true })
      .click();
    await opt()
      .getByRole("button", { name: "Retry exact attempt", exact: true })
      .waitFor();
    const failedBody = posts.at(-1).body;
    await opt().getByLabel("Time limit in seconds", { exact: true }).fill("30");
    await opt()
      .getByRole("button", { name: "Retry exact attempt", exact: true })
      .click();
    await opt()
      .getByRole("heading", { name: "Feasible schedule found", exact: true })
      .waitFor();
    assert.deepEqual(posts.at(-1).body, failedBody);
    check(
      "network retry preserves exact original request despite changed form",
    );
    holdDetail = true;
    await opt()
      .getByRole("button", { name: "Reload saved result", exact: true })
      .click();
    while (!releaseDetail) await page.waitForTimeout(20);
    await opt()
      .locator(".opt-history-item")
      .filter({ hasText: "UNKNOWN" })
      .click();
    await opt()
      .getByRole("heading", {
        name: "No schedule found within the configured limits",
        exact: true,
      })
      .waitFor();
    releaseDetail();
    holdDetail = false;
    await page.waitForTimeout(100);
    assert.equal(
      await opt()
        .getByRole("heading", { name: "Feasible schedule found", exact: true })
        .count(),
      0,
    );
    check("stale run response cannot replace newer selection");
    await page.reload();
    await page.getByRole("button", { name: "PS1 · Hackathon dataset" }).click();
    await page
      .getByText("Connection and saved instances", { exact: true })
      .click();
    await page
      .getByRole("button", { name: "Load saved list", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Browser fixture", exact: true })
      .click();
    await opt()
      .locator(".opt-history-item")
      .filter({ hasText: "FEASIBLE" })
      .click();
    await opt()
      .getByRole("heading", { name: "Feasible schedule found", exact: true })
      .waitFor();
    check("browser refresh can reopen saved instance and result");
    keyConflict = true;
    await opt()
      .getByRole("button", { name: "Generate schedule", exact: true })
      .click();
    await opt()
      .getByRole("alert")
      .filter({ hasText: "Idempotency key" })
      .waitFor();
    const collisionKey = posts.at(-1).body.idempotency_key;
    await opt()
      .getByRole("button", { name: "Generate schedule", exact: true })
      .click();
    await opt()
      .getByText("Saved result safely reused.", { exact: true })
      .waitFor();
    assert.notEqual(posts.at(-1).body.idempotency_key, collisionKey);
    check("idempotency 409 allows a new attempt with a fresh key");
    await page.setViewportSize({ width: 820, height: 1180 });
    await shot("10-tablet");
    check("tablet viewport renders");
    console.log(
      `${checks} browser checks passed; mock API screenshots saved in docs/ui-screenshots.`,
    );
  } catch (e) {
    console.log("VISIBLE TEXT", await page.locator("body").innerText());
    throw e;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
