const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const PROJECT_ROOT = path.resolve(__dirname, "../../../../../../..");
const { loadInternals } = require(path.join(PROJECT_ROOT, "tests/unit/javascript/utils/internals.js"));

const { throwawayMarker } = loadInternals(
  path.join(PROJECT_ROOT, "roles/web-app-discourse/files/playwright/test-rbac.js"),
  ["throwawayMarker"],
  {},
  {},
);

const USER_PROFILE = path.join(
  PROJECT_ROOT,
  "roles/web-app-keycloak/templates/import/components/org.keycloak.userprofile.UserProfileProvider.json.j2",
);
const USERNAME_TAIL = new RegExp(`^${fs.readFileSync(USER_PROFILE, "utf8").match(/_profile\.lookaheads ~ "([^"]+)"/)[1]}`);

const REFUSED_IN_CI = parseInt("mx00guv4", 36);

test("the Keycloak username policy refuses the plain base36 timestamp of the failing CI run", () => {
  assert.equal(USERNAME_TAIL.test(`rename${REFUSED_IN_CI.toString(36)}`), false);
});

test("the throwaway username passes the Keycloak username policy across the timestamps around the failing CI run", () => {
  for (let now = REFUSED_IN_CI; now < REFUSED_IN_CI + 36 ** 3; now += 7) {
    const username = `rename${throwawayMarker(now)}`;
    assert.ok(USERNAME_TAIL.test(username), `${username} breaks the Keycloak username policy`);
  }
});

test("throwaway markers of different timestamps stay distinct", () => {
  assert.notEqual(throwawayMarker(REFUSED_IN_CI), throwawayMarker(REFUSED_IN_CI + 1));
});
