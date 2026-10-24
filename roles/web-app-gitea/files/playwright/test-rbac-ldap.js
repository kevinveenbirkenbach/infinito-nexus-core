const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const {
  decodeDotenvQuotedValue,
  keycloakAdminAddUserToGroup,
  keycloakRemoveUserFromGroupViaRest,
  normalizeBaseUrl,
} = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");

const env = {
  biberUsername: decodeDotenvQuotedValue(process.env.BIBER_USERNAME),
  biberPassword: decodeDotenvQuotedValue(process.env.BIBER_PASSWORD),
  keycloakBaseUrl: normalizeBaseUrl(decodeDotenvQuotedValue(process.env.KEYCLOAK_BASE_URL) || ""),
  realmName: decodeDotenvQuotedValue(process.env.KEYCLOAK_REALM_NAME),
  adminRealm: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_REALM),
  adminClientId: decodeDotenvQuotedValue(process.env.KEYCLOAK_ADMIN_CLI_CLIENT_ID),
  superAdminUsername: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_USERNAME),
  superAdminPassword: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_PASSWORD),
  administratorGroupPath: decodeDotenvQuotedValue(process.env.RBAC_ADMINISTRATOR_GROUP_PATH),
  restrictedGroupPath: decodeDotenvQuotedValue(process.env.RBAC_RESTRICTED_GROUP_PATH),
};

async function signInAsBiber(request, shared) {
  const credentials = Buffer.from(`${env.biberUsername}:${env.biberPassword}`).toString("base64");
  const response = await request.get(`${shared.env.gitEaBaseUrl.replace(/\/$/, "")}/api/v1/user`, {
    headers: { Authorization: `Basic ${credentials}`, Accept: "application/json" },
    timeout: resolveTimeout(30_000),
  });
  const body = await response.text();
  expect(response.ok(), `biber must sign in to Gitea through the LDAP source, got ${response.status()}: ${body.slice(0, 300)}`).toBe(true);
  return JSON.parse(body);
}

async function withBiberInGroup(browser, groupPath, body) {
  const adminOpts = { adminRealm: env.adminRealm, adminClientId: env.adminClientId };
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  let joined = false;
  try {
    joined = await keycloakAdminAddUserToGroup(
      context.request,
      env.keycloakBaseUrl,
      env.realmName,
      groupPath,
      env.biberUsername,
      env.superAdminUsername,
      env.superAdminPassword,
      adminOpts,
    );
    await body(context.request);
  } finally {
    if (joined) {
      await keycloakRemoveUserFromGroupViaRest(
        context.request,
        env.keycloakBaseUrl,
        env.realmName,
        env.superAdminUsername,
        env.superAdminPassword,
        groupPath,
        env.biberUsername,
        adminOpts,
      ).catch((err) => console.warn(`Cleanup removal of biber from ${groupPath} failed: ${err}`));
    }
    await context.close().catch(() => {});
  }
}

exports.register = function (shared) {
  test("rbac: biber without a Gitea role signs in as a regular Gitea user", async ({ browser }) => {
    skipUnlessServiceEnabled("ldap");
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const self = await signInAsBiber(context.request, shared);
      expect(self.login, "the LDAP source must resolve biber's own account").toBe(env.biberUsername);
      expect(self.is_admin, "a realm user outside the administrator role group must not be a Gitea administrator").toBe(false);
      expect(self.restricted, "a realm user outside the restricted role group must not be restricted").toBe(false);
    } finally {
      await context.close().catch(() => {});
    }
  });

  test("rbac: membership in the administrator group makes biber a Gitea administrator", async ({ browser }) => {
    skipUnlessServiceEnabled("sso");
    skipUnlessServiceEnabled("ldap");
    await withBiberInGroup(browser, env.administratorGroupPath, async (request) => {
      await expect
        .poll(async () => (await signInAsBiber(request, shared)).is_admin, {
          timeout: resolveTimeout(60_000),
          message: `biber in ${env.administratorGroupPath} must become a Gitea administrator at the next sign-in`,
        })
        .toBe(true);
    });
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await expect
        .poll(async () => (await signInAsBiber(context.request, shared)).is_admin, {
          timeout: resolveTimeout(60_000),
          message: "leaving the administrator role group must revoke the Gitea administrator flag at the next sign-in",
        })
        .toBe(false);
    } finally {
      await context.close().catch(() => {});
    }
  });

  test("rbac: membership in the restricted group makes biber a restricted Gitea user", async ({ browser }) => {
    skipUnlessServiceEnabled("sso");
    skipUnlessServiceEnabled("ldap");
    await withBiberInGroup(browser, env.restrictedGroupPath, async (request) => {
      await expect
        .poll(async () => (await signInAsBiber(request, shared)).restricted, {
          timeout: resolveTimeout(60_000),
          message: `biber in ${env.restrictedGroupPath} must become a restricted Gitea user at the next sign-in`,
        })
        .toBe(true);
    });
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await expect
        .poll(async () => (await signInAsBiber(context.request, shared)).restricted, {
          timeout: resolveTimeout(60_000),
          message: "leaving the restricted role group must lift the restriction at the next sign-in",
        })
        .toBe(false);
    } finally {
      await context.close().catch(() => {});
    }
  });
};
