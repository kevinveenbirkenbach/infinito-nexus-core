const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const { gotoOnion } = require("./personas");

exports.register = function (shared) {
  test("administrator: administrator role member reaches the Friendica admin panel", async ({ page }) => {
    shared.skipUnlessServiceEnabled("ldap");
    const login = shared.pickLoginPath();
    await login(page, shared.env.adminUsername, shared.env.adminPassword);

    const response = await gotoOnion(page, `${shared.trimmedBaseUrl()}/admin`, { waitUntil: "domcontentloaded" });
    expect(response, "Expected a response for /admin").toBeTruthy();
    expect(
      response.status(),
      "An administrator role member MUST be listed in config.admin_email and reach /admin",
    ).toBeLessThan(400);
    await expect(page.locator("#adminpage").first()).toBeVisible({ timeout: resolveTimeout(30_000) });

    await shared.friendicaLogout(page);
  });

  test("biber: Friendica refuses the admin panel to a user outside the administrator role", async ({ page }) => {
    shared.skipUnlessServiceEnabled("ldap");
    const login = shared.pickLoginPath();
    await login(page, shared.env.biberUsername, shared.env.biberPassword);

    const response = await gotoOnion(page, `${shared.trimmedBaseUrl()}/admin`, { waitUntil: "domcontentloaded" });
    expect(response, "Expected a response for /admin").toBeTruthy();
    expect(response.status(), "biber MUST NOT be a Friendica site administrator").toBe(403);
    await expect(page.locator("#adminpage")).toHaveCount(0);

    await shared.friendicaLogout(page);
  });
};
