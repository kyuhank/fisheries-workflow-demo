import {
  appJwt,
  createGitHub,
  OWNER_ID,
  PERMISSIONS,
  REPOSITORY_ID,
} from "./github.ts";
import { setup } from "./setup.ts";

const assert = (condition: unknown, message = "Assertion failed") => {
  if (!condition) throw Error(message);
};
const decode = (text: string) =>
  Uint8Array.from(
    atob(text.replace(/-/g, "+").replace(/_/g, "/")),
    (c) => c.charCodeAt(0),
  );

async function fixture() {
  const pair = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  );
  const data = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", pair.privateKey),
  );
  const pem = "-----BEGIN PRIVATE KEY-----\n" +
    btoa(String.fromCharCode(...data)) + "\n-----END PRIVATE KEY-----";
  return { pair, app: { app_id: 42, private_key: pem } };
}

Deno.test("App JWT is signed, short lived and identifies the app", async () => {
  const { pair, app } = await fixture();
  const parts = (await appJwt(app)).split(".");
  assert(
    await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      pair.publicKey,
      decode(parts[2]),
      new TextEncoder().encode(parts[0] + "." + parts[1]),
    ),
  );
  const claims = JSON.parse(new TextDecoder().decode(decode(parts[1])));
  assert(claims.iss === "42" && claims.exp - claims.iat <= 600);
});

Deno.test("Installation token cannot expand beyond the paper repository", async () => {
  const originalFetch = globalThis.fetch;
  const { app } = await fixture();
  const calls: any[] = [];
  globalThis.fetch = async (url: any, init?: RequestInit) => {
    calls.push({
      url: String(url),
      body: init?.body && JSON.parse(String(init.body)),
    });
    return Response.json(
      String(url).endsWith("/installation")
        ? { id: 123, account: { id: OWNER_ID }, suspended_at: null }
        : {
          token: "test-installation-token",
          expires_at: new Date(Date.now() + 3600000).toISOString(),
        },
    );
  };
  try {
    const client = createGitHub(async () => [app]);
    await client.installationToken();
    await client.installationToken();
    assert(calls.length === 2, "A valid installation token is cached");
    assert(
      JSON.stringify(calls[1].body) ===
        JSON.stringify({
          repository_ids: [REPOSITORY_ID],
          permissions: PERMISSIONS,
        }),
    );
    assert(!Object.hasOwn(calls[1].body.permissions, "administration"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

Deno.test("Public visitors cannot register or replace an app", async () => {
  const attempts = [
    [{ state: "invalid" }, []],
    [{ state: "a".repeat(64) }, [{ app_id: 42 }]],
    [{ state: "a".repeat(64) }, [{
      app_id: null,
      setup_hash: "wrong",
      setup_expires: "2099-01-01",
    }]],
  ];
  for (const [body, rows] of attempts) {
    let rejected = false;
    try {
      await setup("/setup/manifest", body, async () => rows);
    } catch {
      rejected = true;
    }
    assert(rejected);
  }
});
