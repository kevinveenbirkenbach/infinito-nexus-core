const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");
const { gotoOnion } = require("./personas");

function decodeJwtPayload(token) {
  const segment = String(token || "").split(".")[1] || "";
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(Buffer.from(base64, "base64").toString("utf8"));
}

async function requestRoomToken(shared, page, roomName) {
  await gotoOnion(page, `${shared.env.appBaseUrl}/oidc/redirect?path=/${roomName}`, {
    waitUntil: "domcontentloaded",
  });
  await expect
    .poll(() => new URL(page.url()).searchParams.get("oidc"), {
      timeout: resolveTimeout(60_000),
      message: "the keycloak_adapter round trip must land back on the room with an oidc state",
    })
    .not.toBeNull();
  return new URL(page.url()).searchParams;
}

exports.register = function (shared) {
  test("rbac: the keycloak_adapter issues a moderator JWT to the administrator", async ({ page }) => {
    shared.skipUnlessServiceEnabled("sso");
    shared.skipUnlessServiceEnabled("keycloak_adapter");
    test.setTimeout(resolveTimeout(180_000));
    const roomName = "e2e-admin-jwt-room";
    await shared.runAdminFlow(page, {
      adminInteraction: async (p) => {
        const params = await requestRoomToken(shared, p, roomName);
        expect(params.get("oidc"), "the administrator MUST be authorized by the keycloak_adapter").toBe("authorized");
        const payload = decodeJwtPayload(params.get("jwt"));
        expect(payload.room, "the JWT must be scoped to the requested room").toBe(roomName);
        expect(payload.context?.user?.moderator, "the administrator's JWT MUST mark a moderator").toBe(true);
      },
    });
  });

  test("rbac: the keycloak_adapter refuses a JWT to biber without the administrator role", async ({ page }) => {
    shared.skipUnlessServiceEnabled("sso");
    shared.skipUnlessServiceEnabled("keycloak_adapter");
    test.setTimeout(resolveTimeout(180_000));
    await shared.runBiberFlow(page, {
      biberInteraction: async (p) => {
        const params = await requestRoomToken(shared, p, "e2e-biber-jwt-room");
        expect(params.get("oidc"), "biber MUST NOT receive a moderator JWT").toBe("failed");
        expect(params.get("jwt"), "biber's redirect MUST carry no JWT").toBeNull();
      },
    });
  });
};
