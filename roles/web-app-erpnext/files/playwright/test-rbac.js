const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const {
  decodeDotenvQuotedValue,
  keycloakAdminAddUserToGroup,
  keycloakAdminSetUserAttributes,
  keycloakRemoveUserFromGroupViaRest,
  normalizeBaseUrl,
} = require("./personas");

const rbacEnv = {
  keycloakBaseUrl: normalizeBaseUrl(process.env.KEYCLOAK_BASE_URL || ""),
  realmName: decodeDotenvQuotedValue(process.env.KEYCLOAK_REALM_NAME || ""),
  superAdminUsername: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_USERNAME || ""),
  superAdminPassword: decodeDotenvQuotedValue(process.env.SUPER_ADMIN_PASSWORD || ""),
  biberEmail: decodeDotenvQuotedValue(process.env.BIBER_EMAIL || "").toLowerCase(),
  biberLastname: decodeDotenvQuotedValue(process.env.BIBER_LASTNAME || ""),
  managerGroup: decodeDotenvQuotedValue(process.env.RBAC_GROUP_MANAGER || ""),
};

const LDAP_LOGIN = "/api/method/frappe.integrations.doctype.ldap_settings.ldap_settings.login";

async function withNativeAdministrator(browser, shared, body) {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
    const login = await context.request.post(`${shared.env.erpnextBaseUrl}/api/method/login`, {
      form: { usr: "Administrator", pwd: shared.env.adminNativePassword },
      timeout: resolveTimeout(60_000),
    });
    expect(login.status(), "the break-glass Administrator must sign in through /api/method/login").toBe(200);
    return await body(context.request);
  } finally {
    await context.close().catch(() => {});
  }
}

async function erpnextUser(request, shared, email) {
  const response = await request.get(`${shared.env.erpnextBaseUrl}/api/resource/User/${encodeURIComponent(email)}`, {
    timeout: resolveTimeout(60_000),
  });
  if (response.status() === 404) return null;
  expect(response.status(), `reading the ERPNext user ${email} must succeed`).toBe(200);
  return (await response.json()).data;
}

function roleNames(user) {
  return (user && user.roles ? user.roles : []).map((row) => row.role);
}

async function withBiberIn(browser, shared, groupPath, body) {
  const admin = await browser.newContext({ ignoreHTTPSErrors: true });
  let joined = false;
  try {
    joined = await keycloakAdminAddUserToGroup(
      admin.request,
      rbacEnv.keycloakBaseUrl,
      rbacEnv.realmName,
      groupPath,
      shared.env.biberUsername,
      rbacEnv.superAdminUsername,
      rbacEnv.superAdminPassword,
    );
    await body(admin.request);
  } finally {
    if (joined) {
      await keycloakRemoveUserFromGroupViaRest(
        admin.request,
        rbacEnv.keycloakBaseUrl,
        rbacEnv.realmName,
        rbacEnv.superAdminUsername,
        rbacEnv.superAdminPassword,
        groupPath,
        shared.env.biberUsername,
      ).catch((err) => console.warn(`Cleanup removal of biber from ${groupPath} failed: ${err}`));
    }
    await admin.close().catch(() => {});
  }
}

exports.register = function (shared) {
  test.describe.serial("erpnext RBAC", () => {
    require("./test-login-biber").register(shared);

    test("administrator: the deploy-time reconcile grants System Manager to the administrator group", async ({ page, browser }) => {
      shared.skipUnlessServiceEnabled("sso");
      test.setTimeout(resolveTimeout(180_000)); // OIDC round-trip plus the break-glass API read

      await shared.signInViaErpnextOidc(page, shared.env.adminUsername, shared.env.adminPassword, "administrator");
      const logged = await page.request.get(`${shared.env.erpnextBaseUrl}/api/method/frappe.auth.get_logged_user`);
      expect(logged.status(), "the administrator must hold an ERPNext session after the OIDC sign-in").toBe(200);
      expect(((await logged.json()).message || "").toLowerCase()).toBe(shared.env.adminEmail.toLowerCase());
      await shared.erpnextLogout(page);

      await withNativeAdministrator(browser, shared, async (request) => {
        const user = await erpnextUser(request, shared, shared.env.adminEmail);
        expect(roleNames(user), "members of the administrator group must hold System Manager").toContain("System Manager");
      });
    });

    test("biber: LDAP sign-in without an ERPNext role is refused", async ({ browser }) => {
      shared.skipUnlessServiceEnabled("ldap");
      test.setTimeout(resolveTimeout(120_000)); // directory bind through Frappe

      const context = await browser.newContext({ ignoreHTTPSErrors: true });
      try {
        const response = await context.request.post(`${shared.env.erpnextBaseUrl}${LDAP_LOGIN}`, {
          form: { usr: shared.env.biberUsername, pwd: shared.env.biberPassword },
          timeout: resolveTimeout(60_000),
        });
        expect(response.status(), "the LDAP search string admits only members of a declared role group").not.toBe(200);
      } finally {
        await context.close().catch(() => {});
      }
    });

    test("biber: LDAP sign-in with the manager group syncs the roles and the directory profile", async ({ browser }) => {
      shared.skipUnlessServiceEnabled("ldap");
      shared.skipUnlessServiceEnabled("sso");
      test.setTimeout(resolveTimeout(300_000)); // attribute and group writes to the directory, bind, API read and teardown

      await withBiberIn(browser, shared, rbacEnv.managerGroup, async (request) => {
        let previous = null;
        try {
          previous = await keycloakAdminSetUserAttributes(
            request,
            rbacEnv.keycloakBaseUrl,
            rbacEnv.realmName,
            shared.env.biberUsername,
            { phoneNumber: "+49 30 1112223", phoneNumberAlt: "+49 170 4445556" },
            rbacEnv.superAdminUsername,
            rbacEnv.superAdminPassword,
          );
          const context = await browser.newContext({ ignoreHTTPSErrors: true });
          try {
            const response = await context.request.post(`${shared.env.erpnextBaseUrl}${LDAP_LOGIN}`, {
              form: { usr: shared.env.biberUsername, pwd: shared.env.biberPassword },
              timeout: resolveTimeout(60_000),
            });
            expect(response.status(), `a manager-group member must sign in through LDAP: ${await response.text()}`).toBe(200);
            await context.request.get(`${shared.env.erpnextBaseUrl}/api/method/logout`).catch(() => {});
          } finally {
            await context.close().catch(() => {});
          }

          await withNativeAdministrator(browser, shared, async (adminRequest) => {
            const user = await erpnextUser(adminRequest, shared, rbacEnv.biberEmail);
            expect(user, "the LDAP sign-in must create or update biber").toBeTruthy();
            expect(roleNames(user), "the manager group must grant Sales User").toContain("Sales User");
            expect(roleNames(user), "the manager group must not grant System Manager").not.toContain("System Manager");
            expect(user.last_name, "the directory surname must land in the last name").toBe(rbacEnv.biberLastname);
            expect(user.phone, "the directory telephoneNumber must land in the phone").toBe("+49 30 1112223");
            expect(user.mobile_no, "the directory mobile must land in the mobile number").toBe("+49 170 4445556");
          });
        } finally {
          if (previous) {
            await keycloakAdminSetUserAttributes(
              request,
              rbacEnv.keycloakBaseUrl,
              rbacEnv.realmName,
              shared.env.biberUsername,
              previous,
              rbacEnv.superAdminUsername,
              rbacEnv.superAdminPassword,
            ).catch((err) => console.warn(`Restoring biber's attributes failed: ${err}`));
          }
        }
      });
    });
  });
};
