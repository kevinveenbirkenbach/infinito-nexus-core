const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");

const {
  decodeDotenvQuotedValue,
  keycloakAdminAddUserToGroup,
  keycloakRemoveUserFromGroupViaRest,
  normalizeBaseUrl,
  requireDotenvValue,
} = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { currentUser, signIn, signOut } = require("./funkwhale-session");

const adminUsername = requireDotenvValue(process.env.ADMIN_USERNAME, "ADMIN_USERNAME");
const adminPassword = requireDotenvValue(process.env.ADMIN_PASSWORD, "ADMIN_PASSWORD");
const biberUsername = requireDotenvValue(process.env.BIBER_USERNAME, "BIBER_USERNAME");
const biberPassword = requireDotenvValue(process.env.BIBER_PASSWORD, "BIBER_PASSWORD");
const keycloakBaseUrl = normalizeBaseUrl(requireDotenvValue(process.env.KEYCLOAK_BASE_URL, "KEYCLOAK_BASE_URL"));
const realmName = requireDotenvValue(process.env.KEYCLOAK_REALM_NAME, "KEYCLOAK_REALM_NAME");
const superAdminUsername = decodeDotenvQuotedValue(process.env.SUPER_ADMIN_USERNAME || "");
const superAdminPassword = decodeDotenvQuotedValue(process.env.SUPER_ADMIN_PASSWORD || "");
const moderatorGroupPath = decodeDotenvQuotedValue(process.env.RBAC_MODERATOR_GROUP_PATH || "");

test("administrator: administrator role group grants superuser and every Funkwhale permission", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(resolveTimeout(180_000)); // Keycloak round trip at the proxy plus the Funkwhale LDAP form
  await signIn(page, "administrator", adminUsername, adminPassword);
  const me = await currentUser(page);
  expect(me.is_superuser, "the administrator group maps to is_superuser").toBe(true);
  expect(me.is_staff, "the administrator group maps to is_staff").toBe(true);
  expect(me.permissions, "a superuser holds every Funkwhale permission").toEqual({
    library: true,
    moderation: true,
    settings: true,
  });
  await signOut(page, "administrator");
});

test("biber: moderator role group grants the moderation permission and leaving it revokes it", async ({ page, browser }) => {
  skipUnlessServiceEnabled("ldap");
  skipUnlessServiceEnabled("sso");
  test.setTimeout(resolveTimeout(360_000)); // two Funkwhale sign-ins around a Keycloak group change written back to LDAP
  expect(moderatorGroupPath, "RBAC_MODERATOR_GROUP_PATH must be set").toBeTruthy();
  expect(superAdminUsername, "SUPER_ADMIN_USERNAME must be set").toBeTruthy();
  expect(superAdminPassword, "SUPER_ADMIN_PASSWORD must be set").toBeTruthy();

  let joined = false;
  try {
    joined = await keycloakAdminAddUserToGroup(
      page.request,
      keycloakBaseUrl,
      realmName,
      moderatorGroupPath,
      biberUsername,
      superAdminUsername,
      superAdminPassword,
    );
    await signIn(page, "biber", biberUsername, biberPassword);
    const me = await currentUser(page);
    expect(me.is_superuser, "the moderator group MUST NOT grant superuser").toBe(false);
    expect(me.permissions.moderation, "the moderator group maps to permission_moderation").toBe(true);
    expect(me.permissions.settings, "the moderator group MUST NOT grant permission_settings").toBe(false);
    await signOut(page, "biber");
  } finally {
    if (joined) {
      const cleanupContext = await browser.newContext({ ignoreHTTPSErrors: true });
      try {
        await Promise.race([
          keycloakRemoveUserFromGroupViaRest(
            cleanupContext.request,
            keycloakBaseUrl,
            realmName,
            superAdminUsername,
            superAdminPassword,
            moderatorGroupPath,
            biberUsername,
          ),
          new Promise((_, reject) => setTimeout(() => reject(new Error("group cleanup timed out")), 30_000)),
        ]);
      } catch (err) {
        console.warn(`Cleanup removal of biber from ${moderatorGroupPath} failed: ${err}`);
      } finally {
        await cleanupContext.close().catch(() => {});
      }
    }
  }

  await signIn(page, "biber", biberUsername, biberPassword);
  const after = await currentUser(page);
  expect(after.permissions.moderation, "leaving the moderator group MUST revoke permission_moderation at the next sign-in").toBe(false);
  await signOut(page, "biber");
});

test("biber: account outside the role groups holds no Funkwhale permission", async ({ page }) => {
  skipUnlessServiceEnabled("ldap");
  test.setTimeout(resolveTimeout(180_000)); // Keycloak round trip at the proxy plus the Funkwhale LDAP form
  await signIn(page, "biber", biberUsername, biberPassword);
  const me = await currentUser(page);
  expect(me.is_superuser, "biber holds no administrator group").toBe(false);
  expect(me.is_staff, "biber holds no administrator group").toBe(false);
  expect(me.permissions, "biber holds no Funkwhale role group").toEqual({
    library: false,
    moderation: false,
    settings: false,
  });
  await signOut(page, "biber");
});
