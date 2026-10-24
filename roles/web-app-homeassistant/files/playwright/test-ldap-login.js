const { test, expect } = require("@playwright/test");

const {
  gotoOnion,
  keycloakAdminAddUserToGroup,
  keycloakRemoveUserFromGroupViaRest,
  normalizeBaseUrl,
  requireDotenvValue,
} = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { resolveTimeout } = require("./timeouts");

const ADMIN_PANEL = "ha-config-users ha-data-table";
const CLEANUP_MS = 60_000;

const keycloakBaseUrl = normalizeBaseUrl(process.env.KEYCLOAK_BASE_URL || "");

function directory() {
  return {
    providerName: requireDotenvValue(process.env.LDAP_PROVIDER_NAME, "LDAP_PROVIDER_NAME"),
    biberUsername: requireDotenvValue(process.env.BIBER_USERNAME, "BIBER_USERNAME"),
    biberPassword: requireDotenvValue(process.env.BIBER_PASSWORD, "BIBER_PASSWORD"),
  };
}

function keycloak() {
  return {
    realm: requireDotenvValue(process.env.KEYCLOAK_REALM_NAME, "KEYCLOAK_REALM_NAME"),
    userGroupPath: requireDotenvValue(process.env.RBAC_USER_GROUP_PATH, "RBAC_USER_GROUP_PATH"),
    superAdminUsername: requireDotenvValue(process.env.SUPER_ADMIN_USERNAME, "SUPER_ADMIN_USERNAME"),
    superAdminPassword: requireDotenvValue(process.env.SUPER_ADMIN_PASSWORD, "SUPER_ADMIN_PASSWORD"),
    options: {
      adminRealm: requireDotenvValue(process.env.KEYCLOAK_ADMIN_REALM, "KEYCLOAK_ADMIN_REALM"),
      adminClientId: requireDotenvValue(process.env.KEYCLOAK_ADMIN_CLI_CLIENT_ID, "KEYCLOAK_ADMIN_CLI_CLIENT_ID"),
    },
  };
}

/**
 * Args:
 *   label: what the cleanup step undoes, for the warning it logs.
 *   step: function returning the promise of the cleanup.
 */
async function cleanup(label, step) {
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${CLEANUP_MS} ms`)), resolveTimeout(CLEANUP_MS));
  });
  try {
    await Promise.race([step(), deadline]);
  } catch (err) {
    console.warn(`Cleanup of ${label} failed: ${err}`);
  } finally {
    clearTimeout(timer);
  }
}

exports.register = function (shared) {
  test("biber: the directory sign-in refuses a member of no Home Assistant role group", async ({ page }) => {
    skipUnlessServiceEnabled("ldap");
    const settings = directory();

    await shared.signInWithProvider(page, settings.providerName, settings.biberUsername, settings.biberPassword);

    await expect(
      page.locator(shared.SIGN_IN_ERROR),
      "the directory sign-in must refuse an account outside the administrator and user role groups",
    ).toBeVisible({ timeout: resolveTimeout(30_000) });
    await expect(page.locator(shared.SHELL)).toHaveCount(0);
  });

  test("administrator: directory sign-in → administrator rights → logout", async ({ page, browser }) => {
    skipUnlessServiceEnabled("ldap");
    test.setTimeout(resolveTimeout(180_000)); // directory sign-in, admin panel, logout and the owner's account removal
    const settings = directory();
    let accountId = null;

    try {
      await shared.signInWithProvider(page, settings.providerName, shared.env.adminUsername, shared.env.adminPassword);
      const account = await shared.currentUser(page);
      accountId = account.id;
      expect(account.isOwner, "the directory account must be a user of its own, not the owner").toBe(false);
      expect(account.isAdmin, "a member of the administrator role group must land in system-admin").toBe(true);

      await gotoOnion(page, `${shared.env.baseUrl}/config/users`);
      await expect(
        page.locator(ADMIN_PANEL),
        "a directory administrator must reach the user management of the hub",
      ).toBeVisible({ timeout: resolveTimeout(60_000) });

      await shared.signOut(page);
    } finally {
      if (accountId) {
        await cleanup(`the directory account ${accountId}`, () => shared.removeAccount(browser, accountId));
      }
    }
  });

  test("biber: user role group → directory sign-in without administrator rights → logout", async ({
    page,
    browser,
    request,
  }) => {
    skipUnlessServiceEnabled("ldap");
    test.skip(!keycloakBaseUrl, "KEYCLOAK_BASE_URL is empty: without web-app-keycloak no group membership can be granted");
    test.setTimeout(resolveTimeout(180_000)); // group join, directory sign-in, logout, group leave and the account removal
    const settings = directory();
    const realm = keycloak();
    let joined = false;
    let accountId = null;

    try {
      joined = await keycloakAdminAddUserToGroup(
        request,
        keycloakBaseUrl,
        realm.realm,
        realm.userGroupPath,
        settings.biberUsername,
        realm.superAdminUsername,
        realm.superAdminPassword,
        realm.options,
      );

      await shared.signInWithProvider(page, settings.providerName, settings.biberUsername, settings.biberPassword);
      const account = await shared.currentUser(page);
      accountId = account.id;
      expect(account.isAdmin, "a member of the user role group must land in system-users").toBe(false);

      await shared.signOut(page);
    } finally {
      if (joined) {
        await cleanup(`biber's membership in ${realm.userGroupPath}`, () =>
          keycloakRemoveUserFromGroupViaRest(
            request,
            keycloakBaseUrl,
            realm.realm,
            realm.superAdminUsername,
            realm.superAdminPassword,
            realm.userGroupPath,
            settings.biberUsername,
            realm.options,
          ),
        );
      }
      if (accountId) {
        await cleanup(`the directory account ${accountId}`, () => shared.removeAccount(browser, accountId));
      }
    }
  });
};
