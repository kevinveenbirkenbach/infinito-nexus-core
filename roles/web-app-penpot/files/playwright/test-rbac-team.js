const { apiFetchOnion, decodeDotenvQuotedValue, requireDotenvValue } = require("./personas");
const { resolveTimeout } = require("./timeouts");

const teamId = decodeDotenvQuotedValue(requireDotenvValue(process.env.PENPOT_RBAC_TEAM_ID, "PENPOT_RBAC_TEAM_ID"));
const teamName = decodeDotenvQuotedValue(requireDotenvValue(process.env.PENPOT_RBAC_TEAM_NAME, "PENPOT_RBAC_TEAM_NAME"));

function flag(permissions, name) {
  const kebab = name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
  return permissions[name] ?? permissions[kebab];
}

exports.register = (shared) => {
  const { test, expect, isServiceEnabled, env, penpotNativeLogin, penpotLdapLogin } = shared;

  test("rbac: the platform administrator owns the shared platform team", async ({ page }) => {
    test.skip(
      isServiceEnabled("sso"),
      "under OIDC the administrator's Penpot profile appears with the first sign-in, after the deploy that would create the team",
    );
    test.setTimeout(resolveTimeout(120_000));
    if (isServiceEnabled("ldap")) {
      await penpotLdapLogin(page, env.adminEmail, env.adminPassword);
    } else {
      await penpotNativeLogin(page, env.adminEmail, env.adminPassword);
    }

    const response = await apiFetchOnion(page.request, `${env.baseUrl}/api/rpc/command/get-teams?_fmt=json`, { method: "GET" });
    expect(response.status(), "Expected get-teams to answer for the signed-in administrator").toBe(200);
    const team = (await response.json()).find((candidate) => candidate.id === teamId);
    expect(team, "the deploy must create the shared platform team").toBeTruthy();
    expect(team.name).toBe(teamName);
    expect(flag(team.permissions, "isOwner"), "the platform administrator must own the shared team").toBe(true);
  });
};
