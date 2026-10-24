const { test } = require("@playwright/test");

exports.register = function (shared) {
  test("biber (granted web-app-kix-user via Keycloak): full login flow (KIX → OAuth2-proxy → Keycloak → KIX-LDAP login → KIX UI → universal logout)", async ({ page }) => {
    shared.skipUnlessServiceEnabled("sso");
    shared.skipUnlessServiceEnabled("ldap");
    shared.expectKeycloakAdminEnv();

    await shared.withBiberInGroup(shared.env.kixUserGroupPath, () =>
      shared.runKixLoginLogoutFlow(page, shared.env.biberUsername, shared.env.biberPassword),
    );
  });
};
