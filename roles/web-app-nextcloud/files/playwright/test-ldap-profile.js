const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const { decodeDotenvQuotedValue, keycloakAdminSetUserAttributes, normalizeBaseUrl } = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");

const DIRECTORY_MANAGED_FIELDS = ["phone", "website", "address", "organisation", "role", "biography"];
const KEYCLOAK_PHONE_ATTRIBUTE = "phoneNumber";

const env = {
  keycloakBaseUrl: normalizeBaseUrl(decodeDotenvQuotedValue(process.env.KEYCLOAK_BASE_URL) || ""),
  realmName: decodeDotenvQuotedValue(process.env.KEYCLOAK_REALM_NAME),
  adminRealm: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_REALM),
  adminClientId: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_CLI_CLIENT_ID),
  superAdminUsername: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_USERNAME),
  superAdminPassword: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_PASSWORD),
  ldapCacheTtlSeconds: Number(decodeDotenvQuotedValue(process.env.NEXTCLOUD_LDAP_CACHE_TTL)),
};

exports.register = function (shared) {
  test("biber: nextcloud profile fields synced from the directory are read-only", async ({ browser }) => {
    skipUnlessServiceEnabled("ldap");
    const biberContext = await browser.newContext({ ignoreHTTPSErrors: true });
    const biberPage = await biberContext.newPage();
    try {
      await shared.loginToStandaloneNextcloud(biberPage, shared.env.biberUsername, shared.env.biberPassword);
      const response = await biberPage.request.get(
        new URL("ocs/v2.php/cloud/user/fields?format=json", shared.env.nextcloudBaseUrl).toString(),
        { headers: { "OCS-APIRequest": "true", Accept: "application/json" }, timeout: resolveTimeout(30_000) },
      );
      const body = await response.text();
      expect(response.ok(), `the editable-fields endpoint must answer for biber, got ${response.status()}: ${body.slice(0, 300)}`).toBe(true);
      const editable = JSON.parse(body).ocs.data;
      expect(editable, "the editable-fields endpoint must list the fields Nextcloud still manages itself").toContain("headline");
      for (const field of DIRECTORY_MANAGED_FIELDS) {
        expect(editable, `the ${field} field is synced from the directory and must not be editable in Nextcloud`).not.toContain(field);
      }

      await biberPage.goto(new URL("settings/user", shared.env.nextcloudBaseUrl).toString(), {
        waitUntil: "domcontentloaded",
        timeout: resolveTimeout(60_000),
      });
      await shared.waitForVisibleCandidate(
        biberPage,
        shared.getNextcloudShellCandidates(biberPage),
        resolveTimeout(60_000),
        "Timed out waiting for biber's personal settings in the Nextcloud shell",
      );
      await shared.logoutStandaloneNextcloud(biberPage);
    } finally {
      await biberContext.close().catch(() => {});
    }
  });

  test("biber: a phone number changed in Keycloak reaches Nextcloud on the next directory password login", async ({ browser, request }) => {
    skipUnlessServiceEnabled("sso");
    skipUnlessServiceEnabled("ldap");
    expect(env.ldapCacheTtlSeconds, "NEXTCLOUD_LDAP_CACHE_TTL must be a number of seconds").toBeGreaterThan(0);
    const refreshBudgetMs = (env.ldapCacheTtlSeconds + 90) * 1000;
    test.setTimeout(refreshBudgetMs + resolveTimeout(120_000)); // the LDAP cache TTL of user_ldap plus one Keycloak attribute write and restore

    const phone = `+49301${String(Date.now()).slice(-6)}`;
    const basic = Buffer.from(`${shared.env.biberUsername}:${shared.env.biberPassword}`).toString("base64");
    const adminOpts = { adminRealm: env.adminRealm, adminClientId: env.adminClientId };
    const adminContext = await browser.newContext({ ignoreHTTPSErrors: true });
    let previous = null;
    try {
      previous = await keycloakAdminSetUserAttributes(
        adminContext.request,
        env.keycloakBaseUrl,
        env.realmName,
        shared.env.biberUsername,
        { [KEYCLOAK_PHONE_ATTRIBUTE]: phone },
        env.superAdminUsername,
        env.superAdminPassword,
        adminOpts,
      );

      await expect
        .poll(
          async () => {
            const response = await request.get(new URL("ocs/v2.php/cloud/user?format=json", shared.env.nextcloudBaseUrl).toString(), {
              headers: { "OCS-APIRequest": "true", Accept: "application/json", Authorization: `Basic ${basic}` },
              timeout: resolveTimeout(30_000),
            });
            if (!response.ok()) {
              return `HTTP ${response.status()}`;
            }
            return (await response.json()).ocs.data.phone;
          },
          {
            timeout: refreshBudgetMs,
            intervals: [5_000],
            message: "a password login of biber against the directory must copy the changed telephoneNumber onto the Nextcloud profile",
          },
        )
        .toBe(phone);
    } finally {
      if (previous) {
        await keycloakAdminSetUserAttributes(
          adminContext.request,
          env.keycloakBaseUrl,
          env.realmName,
          shared.env.biberUsername,
          previous,
          env.superAdminUsername,
          env.superAdminPassword,
          adminOpts,
        ).catch((err) => console.warn(`Restoring biber's phone number failed: ${err}`));
      }
      await adminContext.close().catch(() => {});
    }
  });
};
