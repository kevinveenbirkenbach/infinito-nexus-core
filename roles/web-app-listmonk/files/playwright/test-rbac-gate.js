const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const {
  decodeDotenvQuotedValue,
  gotoOnion,
  normalizeBaseUrl,
  performKeycloakLoginForm,
  requireDotenvValue,
} = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");

const appBaseUrl = normalizeBaseUrl(requireDotenvValue(process.env.APP_BASE_URL, "APP_BASE_URL"));
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const biberUsername = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);
const oidcIssuerUrl = normalizeBaseUrl(requireDotenvValue(process.env.OIDC_ISSUER_URL, "OIDC_ISSUER_URL"));

async function signInThroughKeycloak(page, username, password) {
  await gotoOnion(page, `${appBaseUrl}/admin/`, { waitUntil: "domcontentloaded" });
  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(60_000),
      message: "the Listmonk login page must hand over to Keycloak",
    })
    .toContain(`${oidcIssuerUrl}/protocol/openid-connect/auth`);
  await performKeycloakLoginForm(page, username, password);
  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(60_000),
      message: "Keycloak must return to Listmonk",
    })
    .toContain(appBaseUrl);
}

async function usersApiStatus(page) {
  const response = await page.request.get(`${appBaseUrl}/api/users`, {
    failOnStatusCode: false,
    maxRedirects: 0,
    timeout: resolveTimeout(30_000),
  });
  return response.status();
}

exports.register = function () {
  test("rbac: Listmonk admits the administrator as Super Admin", async ({ page }) => {
    skipUnlessServiceEnabled("sso");
    test.setTimeout(resolveTimeout(180_000));
    await signInThroughKeycloak(page, adminUsername, adminPassword);
    expect(await usersApiStatus(page), "the administrator MUST manage Listmonk users").toBe(200);
  });

  test("rbac: Listmonk refuses biber, who holds no manager or viewer role", async ({ page }) => {
    skipUnlessServiceEnabled("sso");
    test.setTimeout(resolveTimeout(180_000));
    await signInThroughKeycloak(page, biberUsername, biberPassword);
    expect(
      await usersApiStatus(page),
      "biber holds no Listmonk role and MUST NOT get a Listmonk session",
    ).not.toBe(200);
    await gotoOnion(page, `${appBaseUrl}/admin/`, { waitUntil: "domcontentloaded" });
    await expect(
      page.locator(".b-sidebar .menu-list"),
      "biber MUST NOT reach the Listmonk dashboard",
    ).toHaveCount(0);
  });
};
