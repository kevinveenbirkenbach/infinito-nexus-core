const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");

const PROJECT_ROOT = path.resolve(__dirname, "../../../../../../..");
const BROKER = path.join(PROJECT_ROOT, "roles/web-app-bluesky/files/login-broker/server.js");
const HANDOFF_COOKIE = "bsky_handoff_done";

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

async function freePort() {
  const probe = http.createServer();
  const port = await listen(probe);
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

async function startUpstream() {
  const received = [];
  const server = http.createServer((req, res) => {
    received.push({ url: req.url, headers: req.headers });
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("social-app");
  });
  const port = await listen(server);
  return { server, port, received };
}

function startBroker(socialAppPort) {
  return new Promise((resolve, reject) => {
    freePort().then((port) => {
      const child = spawn(process.execPath, [BROKER], {
        env: {
          PATH: process.env.PATH,
          BROKER_PORT: String(port),
          SOCIAL_APP_URL: `http://127.0.0.1:${socialAppPort}`,
          PDS_URL: "http://127.0.0.1:9",
          PDS_HANDLE_DOMAIN: "bluesky.example.org",
          BLUESKY_BRIDGE_ENCRYPTION_KEY: `base64:${Buffer.alloc(32, 7).toString("base64")}`,
          SITE_TITLE: "Bluesky",
          OIDC_NAME_CLAIM: "name",
        },
        stdio: ["ignore", "pipe", "pipe"],
      });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk;
      });
      child.stdout.on("data", (chunk) => {
        if (String(chunk).includes("[broker] listening on")) {
          resolve({ child, port });
        }
      });
      child.on("exit", (code) => reject(new Error(`broker exited with ${code}: ${stderr}`)));
    }, reject);
  });
}

function get(port, requestPath, headers) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: "127.0.0.1", port, path: requestPath, method: "GET", headers },
      (res) => {
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => resolve({ status: res.statusCode, body }));
      },
    );
    req.on("error", reject);
    req.end();
  });
}

test("the login broker in front of social-app", async (t) => {
  const upstream = await startUpstream();
  const broker = await startBroker(upstream.port);
  t.after(() => {
    broker.child.removeAllListeners("exit");
    broker.child.kill();
    upstream.server.close();
  });

  await t.test("drops X-Forwarded-Access-Token before it proxies to social-app", async () => {
    const response = await get(broker.port, "/profile?tab=posts", {
      Cookie: `${HANDOFF_COOKIE}=1`,
      "X-Forwarded-Access-Token": "header.payload.signature",
    });

    assert.equal(response.status, 200);
    assert.equal(response.body, "social-app");
    const forwarded = upstream.received.at(-1);
    assert.equal(forwarded.url, "/profile?tab=posts");
    assert.equal("x-forwarded-access-token" in forwarded.headers, false);
  });

  await t.test("keeps the forwarded identity and points Host at social-app", async () => {
    await get(broker.port, "/", {
      Cookie: `${HANDOFF_COOKIE}=1`,
      "X-Forwarded-Access-Token": "header.payload.signature",
      "X-Forwarded-User": "biber",
      "X-Forwarded-Email": "biber@example.org",
    });

    const forwarded = upstream.received.at(-1);
    assert.equal(forwarded.headers["x-forwarded-user"], "biber");
    assert.equal(forwarded.headers["x-forwarded-email"], "biber@example.org");
    assert.equal(forwarded.headers.host, `127.0.0.1:${upstream.port}`);
  });

  await t.test("refuses a handoff without a forwarded user and proxies nothing", async () => {
    const before = upstream.received.length;

    const response = await get(broker.port, "/", {
      "X-Forwarded-Access-Token": "header.payload.signature",
    });

    assert.equal(response.status, 401);
    assert.match(response.body, /Missing X-Forwarded-User/);
    assert.equal(upstream.received.length, before);
  });
});
