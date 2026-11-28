const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const PROJECT_ROOT = path.resolve(__dirname, "../../../../../../..");
const { loadInternals } = require(path.join(PROJECT_ROOT, "tests/unit/javascript/utils/internals.js"));

const { throwawayMarker } = loadInternals(
  path.join(PROJECT_ROOT, "roles/web-app-discourse/files/playwright/test-rbac.js"),
  ["throwawayMarker"],
  {},
  {},
);

const KEYCLOAK_USERNAME_CHARACTERS = /^[a-z1-9]+$/;
const REFUSED_IN_CI = parseInt("mx00guv4", 36);

test("the plain base36 timestamp of the failing CI run carries the digit Keycloak refuses", () => {
  assert.equal(KEYCLOAK_USERNAME_CHARACTERS.test(REFUSED_IN_CI.toString(36)), false);
});

test("the throwaway marker keeps to Keycloak's username characters across the timestamps around the failing CI run", () => {
  for (let now = REFUSED_IN_CI; now < REFUSED_IN_CI + 36 ** 3; now += 7) {
    const marker = throwawayMarker(now);
    assert.ok(KEYCLOAK_USERNAME_CHARACTERS.test(marker), `${marker} breaks the Keycloak username policy`);
  }
});

test("throwaway markers of different timestamps stay distinct", () => {
  assert.notEqual(throwawayMarker(REFUSED_IN_CI), throwawayMarker(REFUSED_IN_CI + 1));
});
