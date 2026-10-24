const { test, expect } = require("./onion-test");
const { resolveTimeout } = require("./timeouts");

const { skipUnlessServiceEnabled } = require("./service-gating");
const { biberUsername, biberPassword, logoutThroughAccountMenu, ssoLoginAndAssertUsername } = require("./_shared");

test.use({ ignoreHTTPSErrors: true });

test("biber: opencloud account menu shows the display name read from the directory", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  skipUnlessServiceEnabled("ldap");

  await ssoLoginAndAssertUsername(page, biberUsername, biberPassword);

  await page.locator("#_userMenuButton").click({ timeout: resolveTimeout(30_000) });
  const accountMenu = page.locator("#account-info-container");
  await expect(accountMenu, "the account menu must open from the top bar").toBeVisible({ timeout: resolveTimeout(30_000) });
  await expect
    .poll(async () => ((await accountMenu.locator("span > span.block").first().textContent()) || "").trim(), {
      timeout: resolveTimeout(30_000),
      message: "OpenCloud must read the display name from OC_LDAP_USER_SCHEMA_DISPLAYNAME, so the account menu shows a name",
    })
    .not.toBe("");
  await page.locator("#_userMenuButton").click({ timeout: resolveTimeout(30_000) });

  await logoutThroughAccountMenu(page);
});
