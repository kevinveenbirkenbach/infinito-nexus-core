from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

SHARED = (
    PROJECT_ROOT / "roles" / "web-app-openpost" / "files" / "playwright" / "_shared.js"
)

STUBS = {
    "node_modules/@playwright/test/package.json": json.dumps(
        {"name": "@playwright/test", "main": "index.js"}
    ),
    "node_modules/@playwright/test/index.js": """
        const tick = () => new Promise((resolve) => setImmediate(resolve));
        function poll(read, options = {}) {
          const run = async (check, negate) => {
            for (let attempt = 0; attempt < 3; attempt += 1) {
              if (check(await read()) !== negate) return;
              await tick();
            }
            throw new Error(options.message || "poll failed");
          };
          const matchers = (negate) => ({
            toBe: (wanted) => run((value) => value === wanted, negate),
            toContain: (wanted) => run((value) => String(value).includes(wanted), negate),
          });
          return { ...matchers(false), not: matchers(true) };
        }
        function expect(target, message) {
          return {
            toBeVisible: async () => {
              if (!(await target.isVisible())) throw new Error(message || "not visible");
            },
            toBeTruthy: () => {
              if (!target) throw new Error(message || "falsy");
            },
          };
        }
        expect.poll = poll;
        module.exports = { test: { skip: () => {} }, expect };
    """,
    "personas.js": """
        module.exports = {
          decodeDotenvQuotedValue: (value) => value,
          normalizeBaseUrl: (value) => String(value || "").replace(/\\/$/, ""),
          performKeycloakLoginForm: async () => {},
          gotoOnion: (page, url) => page.navigate("GET", url, false),
          isOnionUrl: () => false,
        };
    """,
    "service-gating.js": "module.exports = { isServiceEnabled: () => true, skipUnlessServiceEnabled: () => {} };",
    "timeouts.js": "module.exports = { resolveTimeout: (ms) => ms };",
}

RUNNER = """
    const APP = "http://publish.example.onion";
    const PIXELFED = "https://picture.example.test";
    const CODE = "oob-code";
    Object.assign(process.env, {
      APP_BASE_URL: APP,
      PIXELFED_BASE_URL: PIXELFED,
      ADMIN_USERNAME: "administrator",
      ADMIN_EMAIL: "administrator@example.test",
      ADMIN_PASSWORD: "unused",
    });
    const shared = require("./_shared");

    function fakeChromium(grantLeftByEarlierPass) {
      const page = { href: "about:blank", body: "", session: false, intended: "", routes: [], listeners: [], typedCode: "" };
      const serve = (method, href) => {
        const url = new URL(href);
        if (url.origin === PIXELFED && url.pathname === "/oauth/authorize") {
          if (method === "POST") return { status: 200, body: JSON.stringify({ code: CODE }) };
          if (!page.session) {
            page.intended = href;
            return { status: 302, location: `${PIXELFED}/login` };
          }
          if (grantLeftByEarlierPass) return { status: 302, location: `urn:ietf:wg:oauth:2.0:oob?code=${CODE}&state=s` };
          return { status: 200, body: "consent" };
        }
        if (url.origin === PIXELFED && url.pathname === "/login" && method === "POST") {
          page.session = true;
          return { status: 302, location: page.intended || `${PIXELFED}/` };
        }
        return { status: 200, body: url.pathname === "/login" ? "login" : "" };
      };
      const emit = (location) => page.listeners.forEach((listener) => listener({ headers: () => (location ? { location } : {}) }));
      const routed = (method, href, route) =>
        new Promise((resolve, reject) => {
          const handle = {
            request: () => ({ method: () => method }),
            continue: async () => resolve(serve(method, href)),
            fetch: async () => {
              const raw = serve(method, href);
              return { raw, headers: () => (raw.location ? { location: raw.location } : {}) };
            },
            fulfill: async (options) => resolve(options.response ? options.response.raw : { status: options.status, body: options.body }),
          };
          Promise.resolve(route.handler(handle)).catch(reject);
        });
      page.navigate = async (method, href, formSubmission) => {
        const route = page.routes.find((entry) => entry.matcher(new URL(href)));
        let result = route ? await routed(method, href, route) : serve(method, href);
        let current = href;
        while (result.status === 302) {
          if (!/^https?:/.test(result.location)) {
            if (formSubmission) {
              page.href = "chrome-error://chromewebdata/";
              page.body = "The information you're about to submit is not secure";
              return;
            }
            emit(result.location);
            return;
          }
          emit(result.location);
          current = result.location;
          result = serve("GET", current);
        }
        emit("");
        page.href = current;
        page.body = result.body;
      };
      page.url = () => page.href;
      page.on = (_event, listener) => page.listeners.push(listener);
      page.off = (_event, listener) => {
        page.listeners = page.listeners.filter((entry) => entry !== listener);
      };
      page.route = async (matcher, handler) => page.routes.push({ matcher, handler });
      page.unroute = async (_matcher, handler) => {
        page.routes = page.routes.filter((entry) => entry.handler !== handler);
      };
      const password = { isVisible: async () => page.href === `${PIXELFED}/login`, fill: async () => {} };
      const submit = { click: () => page.navigate("POST", `${PIXELFED}/login`, true) };
      const card = { isVisible: async () => page.href.startsWith(APP), getByRole: () => ({ click: async () => {} }) };
      const dialog = {
        getByRole: (role, { name }) =>
          role === "textbox"
            ? { fill: async () => {} }
            : {
                click: async () => {
                  if (name.source === "^connect$") {
                    await page.navigate("GET", `${PIXELFED}/oauth/authorize?client_id=1&state=s`, false);
                  }
                },
              },
      };
      const locators = {
        'input[name="password"]': password,
        'input[name="email"]': { fill: async () => {} },
        form: { filter: () => ({ locator: () => submit }) },
        '[data-testid="provider-card-pixelfed"]': card,
        body: { innerText: async () => page.body },
      };
      page.locator = (selector) => locators[selector];
      page.getByRole = (role, { name }) => {
        if (role === "dialog") return dialog;
        if (name.source === "^authorize$") {
          return {
            isVisible: async () => page.body === "consent",
            click: () => page.navigate("POST", `${PIXELFED}/oauth/authorize`, true),
          };
        }
        if (role === "textbox") return { fill: async (value) => { page.typedCode = value; } };
        if (/connect account/.test(name.source)) return { click: async () => { page.href = `${APP}/accounts`; } };
        return { isVisible: async () => Boolean(page.typedCode) };
      };
      return page;
    }

    (async () => {
      const page = fakeChromium(process.argv[2] === "grant");
      try {
        await shared.connectPixelfedAccount(page, "administrator");
        process.stdout.write(JSON.stringify({ typedCode: page.typedCode, href: page.href }));
      } catch (error) {
        process.stdout.write(JSON.stringify({ error: error.message, href: page.href }));
      }
    })();
"""


@unittest.skipUnless(shutil.which("node"), "node is not available in PATH")
class TestPixelfedOobCapture(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(prefix="openpost-pixelfed-"))
        for relative, source in {**STUBS, "run.js": RUNNER}.items():
            target = self.workdir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(source))
        shutil.copy(str(SHARED), str(self.workdir / "_shared.js"))

    def tearDown(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def _connect(self, mode: str) -> dict:
        """Args:
            mode: "grant" when an earlier pass left Pixelfed's grant, else "fresh".

        Returns:
            The code typed into OpenPost and the final URL, or the error raised.
        """
        proc = subprocess.run(
            ["node", "run.js", mode],
            capture_output=True,
            text=True,
            cwd=str(self.workdir),
            timeout=20,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        return json.loads(proc.stdout)

    def test_a_grant_from_an_earlier_pass_still_yields_the_oob_code(self) -> None:
        result = self._connect("grant")
        self.assertNotIn("error", result, result)
        self.assertEqual(
            result["typedCode"],
            "oob-code",
            "the onion pass follows the clearnet pass, so Passport skips the consent "
            "screen and redirects to the urn: OOB URI; inside the sign-in form's "
            "redirect chain Chromium stops that at its insecure-form interstitial",
        )

    def test_a_fresh_instance_still_goes_through_the_consent_screen(self) -> None:
        result = self._connect("fresh")
        self.assertNotIn("error", result, result)
        self.assertEqual(result["typedCode"], "oob-code")


if __name__ == "__main__":
    unittest.main()
