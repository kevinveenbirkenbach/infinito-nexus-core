const { expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");

const {
  decodeDotenvQuotedValue,
  gotoOnion,
  normalizeBaseUrl,
  performKeycloakLoginForm,
  requireDotenvValue,
} = require("./personas");
const { isServiceEnabled, skipUnlessServiceEnabled } = require("./service-gating");
const keycloakAdmin = require("./personas/utils/keycloak");

const oidcEnabled         = isServiceEnabled("sso");
const ldapEnabled         = isServiceEnabled("ldap");
const oidcIssuerUrl       = normalizeBaseUrl(requireDotenvValue(process.env.OIDC_ISSUER_URL, "OIDC_ISSUER_URL"));
const semaphoreBaseUrl    = normalizeBaseUrl(process.env.SEMAPHORE_BASE_URL || "");
const adminUsername       = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword       = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);
const breakglassUsername  = decodeDotenvQuotedValue(process.env.BREAKGLASS_USERNAME);
const breakglassPassword  = decodeDotenvQuotedValue(process.env.BREAKGLASS_PASSWORD);
const biberUsername       = decodeDotenvQuotedValue(process.env.BIBER_USERNAME);
const biberPassword       = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD);
const biberEmail          = decodeDotenvQuotedValue(process.env.BIBER_EMAIL);
const canonicalDomain     = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN);
const keycloakBaseUrl     = normalizeBaseUrl(requireDotenvValue(process.env.KEYCLOAK_BASE_URL, "KEYCLOAK_BASE_URL"));
const realmName           = decodeDotenvQuotedValue(process.env.KEYCLOAK_REALM_NAME);
const superAdminUsername  = decodeDotenvQuotedValue(process.env.SUPER_ADMIN_USERNAME);
const superAdminPassword  = decodeDotenvQuotedValue(process.env.SUPER_ADMIN_PASSWORD);
const keycloakAdminRealm  = decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_REALM);
const keycloakAdminCliClientId = decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_CLI_CLIENT_ID);
const userGroupPath       = decodeDotenvQuotedValue(process.env.RBAC_USER_GROUP_PATH);

const LOGIN_PATH = "/auth/login";

function onLoginPage(page) {
  return page.url().includes(LOGIN_PATH);
}

async function gotoLogin(page) {
  await gotoOnion(page, `${semaphoreBaseUrl}${LOGIN_PATH}`, { waitUntil: "domcontentloaded" });
}

async function assertAuthenticated(page, label) {
  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(60_000),
      message: `${label}: expected to leave the Semaphore login page`,
    })
    .not.toContain(LOGIN_PATH);
  await expect(
    page.locator("header, nav, .v-navigation-drawer, .v-app-bar").first(),
    `${label}: authenticated Semaphore chrome must be visible`,
  ).toBeVisible({ timeout: resolveTimeout(60_000) });
}

async function fillLocalLogin(page, username, password) {
  const userField = page.locator("#auth-username").first();
  await userField.waitFor({ state: "visible", timeout: resolveTimeout(30_000) });
  await userField.fill(username);
  await page.locator("#auth-password").first().fill(password);
  await page
    .locator('[data-testid="auth-signin"]')
    .first()
    .click({ timeout: resolveTimeout(30_000) })
    .catch(() => page.keyboard.press("Enter"));
}

async function signInViaLocal(page, username, password, label) {
  await gotoLogin(page);
  await fillLocalLogin(page, username, password);
  await assertAuthenticated(page, label);
}

async function signInViaLdap(page, username, password, label) {
  await signInViaLocal(page, username, password, label);
}

async function signInViaOidc(page, username, password, label) {
  await gotoLogin(page);

  const oidcButton = page
    .locator("a, button")
    .filter({ hasText: /sign\s*in\s*with|keycloak|single\s*sign|sso/i })
    .first();
  await expect(
    oidcButton,
    `${label}: the "Sign in with Keycloak" button must render on the Semaphore login page`,
  ).toBeVisible({ timeout: resolveTimeout(30_000) });
  await oidcButton.click({ timeout: resolveTimeout(30_000) });

  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(60_000),
      message: `${label}: expected redirect to Keycloak OIDC auth (${oidcIssuerUrl}/protocol/openid-connect/auth)`,
    })
    .toContain(`${oidcIssuerUrl}/protocol/openid-connect/auth`);

  await performKeycloakLoginForm(page, username, password);
  await assertAuthenticated(page, label);
}

async function openAccountMenu(page) {
  const trigger = page
    .locator(
      'header button:has(.mdi-account), header button:has(.mdi-account-circle), header .v-avatar, button[aria-label*="account" i], header [role="button"]:has(.mdi-account)',
    )
    .first();
  if (await trigger.count()) {
    await trigger.click().catch(() => {});
  }
}

async function logout(page, label = "session") {
  await openAccountMenu(page);
  const signOut = page
    .locator('a, button, .v-list-item, [role="menuitem"]')
    .filter({ hasText: /sign\s*out|log\s*out|logout|abmelden/i })
    .first();
  if (await signOut.count()) {
    await signOut.click({ timeout: resolveTimeout(30_000) }).catch(() => {});
  }
  await page.waitForTimeout(resolveTimeout(1500));
  if (!onLoginPage(page)) {
    await page.context().clearCookies();
    await gotoLogin(page);
  }
  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(30_000),
      message: `${label}: expected logged-out landing on the Semaphore login page`,
    })
    .toContain(LOGIN_PATH);
}

/**
 * Return Semaphore's record of the signed-in account from /api/user.
 *
 * Args:
 *   page: a Playwright page whose context carries the Semaphore session.
 */
async function currentUser(page) {
  const response = await page.request.get(`${semaphoreBaseUrl}/api/user`, {
    failOnStatusCode: false,
    timeout: resolveTimeout(30_000),
  });
  expect(response.status(), "Semaphore must answer /api/user for a signed-in session").toBe(200);
  return response.json();
}

/**
 * Submit the LDAP login form and return the status Semaphore answers the
 * login request with.
 *
 * Args:
 *   page: the Playwright page to drive.
 *   username: the directory login name.
 *   password: the directory password.
 */
async function submitLdapLogin(page, username, password) {
  await gotoLogin(page);
  const loginResponse = page.waitForResponse(
    (response) => response.url().includes("/api/auth/login") && response.request().method() === "POST",
    { timeout: resolveTimeout(60_000) },
  );
  await fillLocalLogin(page, username, password);
  return (await loginResponse).status();
}

/**
 * Run `fn` while biber is a member of the Keycloak group at `groupPath`,
 * removing the membership afterwards only when this call granted it.
 *
 * Args:
 *   browser: the Playwright browser, used for an isolated admin context.
 *   groupPath: the full Keycloak group path, with leading slash.
 *   fn: async body executed while the membership holds.
 */
async function withBiberInGroup(browser, groupPath, fn) {
  const adminOpts = { adminRealm: keycloakAdminRealm, adminClientId: keycloakAdminCliClientId };
  const adminCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  let biberAdded = false;
  try {
    biberAdded = await keycloakAdmin.keycloakAdminAddUserToGroup(
      adminCtx.request,
      keycloakBaseUrl,
      realmName,
      groupPath,
      biberUsername,
      superAdminUsername,
      superAdminPassword,
      adminOpts,
    );
    return await fn();
  } finally {
    if (biberAdded) {
      await keycloakAdmin
        .keycloakRemoveUserFromGroupViaRest(
          adminCtx.request,
          keycloakBaseUrl,
          realmName,
          superAdminUsername,
          superAdminPassword,
          groupPath,
          biberUsername,
          adminOpts,
        )
        .catch((err) => console.warn(`Cleanup removal of biber from ${groupPath} failed: ${err}`));
    }
    await adminCtx.close().catch(() => {});
  }
}

async function beforeEach({ page }) {
  await page.setViewportSize({ width: 1440, height: 1100 });
  expect(semaphoreBaseUrl, "SEMAPHORE_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  await page.context().clearCookies();
}

module.exports = {
  env: {
    oidcEnabled,
    ldapEnabled,
    oidcIssuerUrl,
    semaphoreBaseUrl,
    adminUsername,
    adminPassword,
    breakglassUsername,
    breakglassPassword,
    biberUsername,
    biberPassword,
    biberEmail,
    canonicalDomain,
    userGroupPath,
  },
  LOGIN_PATH,
  gotoLogin,
  onLoginPage,
  assertAuthenticated,
  currentUser,
  signInViaLocal,
  signInViaLdap,
  signInViaOidc,
  submitLdapLogin,
  withBiberInGroup,
  logout,
  beforeEach,
  skipUnlessServiceEnabled,
};
