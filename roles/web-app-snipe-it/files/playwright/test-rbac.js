const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { normalizeBaseUrl, decodeDotenvQuotedValue, performKeycloakLoginForm, gotoOnion } = require("./personas");
const keycloakAdmin = require("./personas/utils/keycloak");

const env = {
  baseUrl: normalizeBaseUrl(process.env.SNIPE_IT_BASE_URL || ""),
  oidcIssuerUrl: normalizeBaseUrl(process.env.OIDC_ISSUER_URL || ""),
  keycloakBaseUrl: normalizeBaseUrl(process.env.KEYCLOAK_BASE_URL || ""),
  realmName: decodeDotenvQuotedValue(process.env.KEYCLOAK_REALM_NAME || ""),
  keycloakAdminUsername: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_USERNAME || ""),
  keycloakAdminPassword: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_PASSWORD || ""),
  keycloakAdminRealm: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_REALM || ""),
  keycloakAdminCliClientId: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_CLI_CLIENT_ID || ""),
  administratorGroupPath: decodeDotenvQuotedValue(process.env.SNIPE_IT_ADMINISTRATOR_GROUP_PATH || ""),
  userGroupPath: decodeDotenvQuotedValue(process.env.SNIPE_IT_USER_GROUP_PATH || ""),
  permissionGroup: decodeDotenvQuotedValue(process.env.SNIPE_IT_USER_PERMISSION_GROUP || ""),
  protectedJson: decodeDotenvQuotedValue(process.env.SNIPE_IT_RBAC_PROTECTED_JSON || ""),
  adminUsername: decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || ""),
  adminPassword: decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || ""),
  biberUsername: decodeDotenvQuotedValue(process.env.BIBER_USERNAME || ""),
  biberPassword: decodeDotenvQuotedValue(process.env.BIBER_PASSWORD || ""),
};

const adminOpts = () => ({ adminRealm: env.keycloakAdminRealm, adminClientId: env.keycloakAdminCliClientId });

test.use({ ignoreHTTPSErrors: true });

function expectEnv() {
  for (const [key, value] of Object.entries(env)) {
    expect(value, `${key} must be set`).toBeTruthy();
  }
}

async function signInThroughGate(page, username, password) {
  await gotoOnion(page, `${env.baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await expect
    .poll(() => page.url(), {
      timeout: resolveTimeout(60_000),
      message: `expected ${username} to be sent to Keycloak by the oauth2-proxy gate on /login`,
    })
    .toContain(`${env.oidcIssuerUrl}/protocol/openid-connect/auth`);
  await performKeycloakLoginForm(page, username, password);
}

async function reachSnipeItShell(page, username, password) {
  await signInThroughGate(page, username, password);
  const shell = page.locator(".main-header .navbar");
  const directoryForm = page.locator('form:has(input[name="password"])');
  await expect(
    shell.or(directoryForm).first(),
    `expected ${username} to land on Snipe-IT, either signed in through the header bridge or on its directory login form`,
  ).toBeVisible({ timeout: resolveTimeout(60_000) });
  if (!(await shell.isVisible())) {
    await directoryForm.locator('input[name="username"]').fill(username);
    await directoryForm.locator('input[name="password"]').fill(password);
    await directoryForm.locator('[type="submit"]').first().click({ timeout: resolveTimeout(30_000) });
  }
  await expect(shell, `expected ${username} to reach the Snipe-IT authenticated shell`).toBeVisible({
    timeout: resolveTimeout(60_000),
  });
}

async function settingsStatus(page) {
  const response = await page.request.get(`${env.baseUrl}/admin`, { maxRedirects: 0 });
  return response.status();
}

async function snipeItApi(page, method, path, body) {
  return page.evaluate(
    async ({ method, path, body }) => {
      const csrf = document.querySelector('meta[name="csrf-token"]');
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRF-TOKEN": csrf ? csrf.getAttribute("content") : "",
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: response.status, json: await response.json().catch(() => null) };
    },
    { method, path, body },
  );
}

async function snipeItUsers(page) {
  const result = await snipeItApi(page, "GET", "/api/v1/users?limit=500");
  expect(result.status, "the administrator session must read the Snipe-IT users API").toBe(200);
  return result.json.rows;
}

async function ldapTestLogin(page, username, password) {
  return snipeItApi(page, "POST", "/api/v1/settings/ldaptestlogin", {
    ldaptest_user: username,
    ldaptest_password: password,
  });
}

async function keycloakGroupMembers(request, groupPath) {
  const token = await keycloakAdmin.keycloakAdminToken(
    request,
    env.keycloakBaseUrl,
    env.keycloakAdminUsername,
    env.keycloakAdminPassword,
    adminOpts(),
  );
  const groupId = await keycloakAdmin.keycloakResolveGroupId(request, env.keycloakBaseUrl, env.realmName, token, groupPath);
  const response = await request.get(
    `${env.keycloakBaseUrl}/admin/realms/${encodeURIComponent(env.realmName)}/groups/${groupId}/members?max=1000`,
    { headers: { Authorization: `Bearer ${token}` }, timeout: resolveTimeout(30_000) },
  );
  expect(response.ok(), `Keycloak members of ${groupPath} must be readable`).toBe(true);
  return (await response.json()).map((member) => member.username);
}

async function withContext(browser, fn) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    return await fn(await context.newPage());
  } finally {
    await context.close().catch(() => {});
  }
}

const isSuperuser = (user) => String((user.permissions || {}).superuser) === "1";
const holdsAdmin = (user) => String((user.permissions || {}).admin) === "1";
const inPermissionGroup = (user) =>
  Boolean(user.groups && user.groups.rows.some((group) => group.name === env.permissionGroup));

test("biber: the proxy refuses a persona holding none of the Snipe-IT role groups", async ({ page }) => {
  skipUnlessServiceEnabled("sso");
  expect(env.baseUrl, "SNIPE_IT_BASE_URL must be set").toBeTruthy();
  expect(env.biberUsername, "BIBER_USERNAME must be set").toBeTruthy();
  expect(env.biberPassword, "BIBER_PASSWORD must be set").toBeTruthy();

  await signInThroughGate(page, env.biberUsername, env.biberPassword);

  await expect(page.locator(".main-header .navbar"), {
    message:
      "biber reached the Snipe-IT shell; meta/services.yml admits only the administrator and user role groups and biber holds neither",
  }).toHaveCount(0, { timeout: resolveTimeout(30_000) });
  await expect(page.locator("body"), {
    message: "the page is neither Snipe-IT nor a recognisable denial; the proxy may have changed its rejection wording",
  }).toContainText(/403|forbidden|permission|unauthorized|access denied/i, { timeout: resolveTimeout(60_000) });
});

test("administrator: the deploy-time reconcile leaves superuser and the permission group only on role-group members", async ({ browser }) => {
  skipUnlessServiceEnabled("sso");
  test.setTimeout(resolveTimeout(180_000)); // one Keycloak sign-in plus the Keycloak admin token and member reads
  expectEnv();
  const protectedUsernames = JSON.parse(env.protectedJson);

  const adminRequest = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    const administrators = await keycloakGroupMembers(adminRequest.request, env.administratorGroupPath);
    const members = new Set([...administrators, ...(await keycloakGroupMembers(adminRequest.request, env.userGroupPath))]);

    await withContext(browser, async (page) => {
      await reachSnipeItShell(page, env.adminUsername, env.adminPassword);
      expect(await settingsStatus(page), "the bootstrap administrator must reach the Snipe-IT settings at /admin").toBe(200);

      const accounts = (await snipeItUsers(page)).filter((user) => !protectedUsernames.includes(user.username));
      const usernames = new Set(accounts.map((user) => user.username));
      const missing = [...members].filter((username) => !protectedUsernames.includes(username) && !usernames.has(username));
      expect(missing, "every role-group member must have a Snipe-IT account after the deploy").toEqual([]);

      const strayAdmins = accounts
        .filter((user) => (isSuperuser(user) || holdsAdmin(user)) && !administrators.includes(user.username))
        .map((user) => user.username);
      expect(strayAdmins, "rbac_sync.php must demote every superuser or admin outside the administrator role group").toEqual([]);

      const unpromoted = accounts
        .filter((user) => administrators.includes(user.username) && !isSuperuser(user))
        .map((user) => user.username);
      expect(unpromoted, "rbac_sync.php must promote every administrator role-group member to superuser").toEqual([]);

      const ungrouped = accounts
        .filter((user) => members.has(user.username) && !inPermissionGroup(user))
        .map((user) => user.username);
      expect(ungrouped, `every role-group member must join the ${env.permissionGroup} permission group`).toEqual([]);
    });
  } finally {
    await adminRequest.close().catch(() => {});
  }
});

test("biber: the user role group admits biber through the LDAP filter and the gate, with every mapped directory field and no admin rights", async ({ browser }) => {
  skipUnlessServiceEnabled("sso");
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(resolveTimeout(360_000)); // three Keycloak sign-ins plus the LDAP sync POST, which rewrites every directory member
  expectEnv();

  const marker = Date.now().toString(36);
  const digits = String(Date.now()).slice(-7);
  const profile = {
    nickname: `Biber ${marker}`,
    idNumber: `E-${marker}`,
    phoneNumber: `+49 30 ${digits}`,
    phoneNumberAlt: `+49 170 ${digits}`,
    title: `Asset keeper ${marker}`,
    department: `Inventory ${marker}`,
    street: `Biberweg ${marker}`,
    locality: `Biberstadt ${marker}`,
    region: `Biberland ${marker}`,
    postal_code: `P${digits}`,
    country: "IS",
  };
  const expectedFields = {
    display_name: profile.nickname,
    employee_num: profile.idNumber,
    phone: profile.phoneNumber,
    mobile: profile.phoneNumberAlt,
    jobtitle: profile.title,
    address: profile.street,
    city: profile.locality,
    state: profile.region,
    zip: profile.postal_code,
    country: profile.country,
  };
  const adminRequest = await browser.newContext({ ignoreHTTPSErrors: true });
  let previousProfile = null;
  let biberJoined = false;
  try {
    previousProfile = await keycloakAdmin.keycloakAdminSetUserAttributes(
      adminRequest.request,
      env.keycloakBaseUrl,
      env.realmName,
      env.biberUsername,
      profile,
      env.keycloakAdminUsername,
      env.keycloakAdminPassword,
      adminOpts(),
    );

    await withContext(browser, async (page) => {
      await reachSnipeItShell(page, env.adminUsername, env.adminPassword);

      const refusedBiber = await ldapTestLogin(page, env.biberUsername, env.biberPassword);
      expect(refusedBiber.status, "the Snipe-IT LDAP filter must refuse biber while biber holds no role group").toBe(400);
      expect(String((refusedBiber.json || {}).message)).toMatch(/did not successfully bind/i);

      const refusedAdmin = await ldapTestLogin(page, env.adminUsername, env.adminPassword);
      expect(refusedAdmin.status, "the Snipe-IT LDAP filter must leave out the bootstrap administrator").toBe(400);
      expect(String((refusedAdmin.json || {}).message)).toMatch(/did not successfully bind/i);

      biberJoined = await keycloakAdmin.keycloakAdminAddUserToGroup(
        adminRequest.request,
        env.keycloakBaseUrl,
        env.realmName,
        env.userGroupPath,
        env.biberUsername,
        env.keycloakAdminUsername,
        env.keycloakAdminPassword,
        adminOpts(),
      );

      const admittedBiber = await ldapTestLogin(page, env.biberUsername, env.biberPassword);
      expect(admittedBiber.status, "the Snipe-IT LDAP filter must admit biber once biber holds the user role group").toBe(200);

      await gotoOnion(page, `${env.baseUrl}/users/ldap`, { waitUntil: "domcontentloaded" });
      await page.locator("#sync").click({ timeout: resolveTimeout(30_000) });
      const biberRow = page.locator("#customFieldsTable tbody tr").filter({ hasText: env.biberUsername }).first();
      await expect(biberRow, "the LDAP sync must import biber once biber holds the user role group").toBeVisible({
        timeout: resolveTimeout(120_000),
      });
      await expect(biberRow).toContainText(profile.nickname);
      await expect(biberRow).toContainText(profile.idNumber);

      const biber = (await snipeItUsers(page)).find((user) => user.username === env.biberUsername);
      expect(biber, "the LDAP sync must leave a Snipe-IT account for biber").toBeTruthy();
      for (const [field, value] of Object.entries(expectedFields)) {
        expect(biber[field], `Snipe-IT field ${field} must carry the directory value`).toBe(value);
      }
      expect((biber.department || {}).name, "Snipe-IT must file biber under the directory department").toBe(profile.department);

      await gotoOnion(page, `${env.baseUrl}/users/${biber.id}`, { waitUntil: "domcontentloaded" });
      await expect(page.locator("body"), "the user page must show the directory phone").toContainText(profile.phoneNumber);
      await expect(page.locator("body"), "the user page must show the directory job title").toContainText(profile.title);
    });

    await withContext(browser, async (page) => {
      await reachSnipeItShell(page, env.biberUsername, env.biberPassword);
      expect(
        await settingsStatus(page),
        "biber holds only the user role group and must not reach the Snipe-IT settings at /admin",
      ).not.toBe(200);
    });
  } finally {
    if (biberJoined) {
      await keycloakAdmin
        .keycloakRemoveUserFromGroupViaRest(
          adminRequest.request,
          env.keycloakBaseUrl,
          env.realmName,
          env.keycloakAdminUsername,
          env.keycloakAdminPassword,
          env.userGroupPath,
          env.biberUsername,
          adminOpts(),
        )
        .catch((err) => console.warn(`Cleanup removal of biber from ${env.userGroupPath} failed: ${err}`));
    }
    if (previousProfile) {
      await keycloakAdmin
        .keycloakAdminSetUserAttributes(
          adminRequest.request,
          env.keycloakBaseUrl,
          env.realmName,
          env.biberUsername,
          previousProfile,
          env.keycloakAdminUsername,
          env.keycloakAdminPassword,
          adminOpts(),
        )
        .catch((err) => console.warn(`Cleanup restore of biber's profile failed: ${err}`));
    }
    await adminRequest.close().catch(() => {});
  }
});
