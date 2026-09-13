/** Repository-scoped installation tokens; no GitHub credential reaches the browser. */
export const REPOSITORY = "kyuhank/fisheries-workflow-demo";
export const REPOSITORY_ID = 1367765865;
export const OWNER_ID = 51262923;
export const WORKFLOW = ".github/workflows/live.yml";
export const PERMISSIONS = { actions: "write", contents: "read" };

export const base64url = (data: Uint8Array) =>
  btoa(String.fromCharCode(...data))
    .replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");

// GitHub supplies a PKCS#1 RSA key; Web Crypto imports PKCS#8.
export function pkcs8(pem: string): Uint8Array {
  const raw = Uint8Array.from(
    atob(pem.replace(/-----[^-]+-----|\s/g, "")),
    (c) => c.charCodeAt(0),
  );
  if (pem.includes("BEGIN PRIVATE KEY")) return raw;
  if (!pem.includes("BEGIN RSA PRIVATE KEY")) {
    throw Error("Unsupported app key.");
  }
  const der = (tag: number, value: Uint8Array) => {
    const length = value.length;
    const size = length < 128
      ? [length]
      : length < 256
      ? [129, length]
      : [130, length >> 8, length & 255];
    return new Uint8Array([tag, ...size, ...value]);
  };
  const rsa = [48, 13, 6, 9, 42, 134, 72, 134, 247, 13, 1, 1, 1, 5, 0];
  return der(48, new Uint8Array([2, 1, 0, ...rsa, ...der(4, raw)]));
}

export async function appJwt(
  app: { app_id: number; private_key: string },
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const encode = (value: unknown) =>
    base64url(new TextEncoder().encode(JSON.stringify(value)));
  const unsigned = encode({ alg: "RS256", typ: "JWT" }) + "." +
    encode({ iat: now - 60, exp: now + 540, iss: String(app.app_id) });
  const key = await crypto.subtle.importKey(
    "pkcs8",
    new Uint8Array(pkcs8(app.private_key)).buffer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned),
  );
  return unsigned + "." + base64url(new Uint8Array(signature));
}

export async function githubApi(
  path: string,
  token?: string,
  method = "GET",
  body?: unknown,
) {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
    "User-Agent": "fisheries-workflow-demo",
  };
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch("https://api.github.com/" + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw Error("The paper demonstration connection is unavailable.");
  }
  return response.status === 204 ? null : await response.json();
}

export function createGitHub(
  db: (path: string, method?: string, body?: unknown) => Promise<any>,
) {
  let cached: { token: string; expires: number } | undefined;
  async function installationToken() {
    if (cached && cached.expires > Date.now() + 60_000) return cached.token;
    const [app] = await db("paper_app?id=eq.true&select=app_id,private_key");
    if (!app?.app_id || !app.private_key) {
      throw Error("The paper demonstration is not connected yet.");
    }
    const jwt = await appJwt(app);
    const installation = await githubApi(
      "repos/" + REPOSITORY + "/installation",
      jwt,
    );
    if (installation.account.id !== OWNER_ID || installation.suspended_at) {
      throw Error("The paper app installation is unavailable.");
    }
    const result = await githubApi(
      "app/installations/" + installation.id + "/access_tokens",
      jwt,
      "POST",
      {
        repository_ids: [REPOSITORY_ID],
        permissions: PERMISSIONS,
      },
    );
    cached = { token: result.token, expires: Date.parse(result.expires_at) };
    return cached.token;
  }
  return {
    installationToken,
    request: async (path: string, method = "GET", body?: unknown) =>
      githubApi(
        "repos/" + REPOSITORY + "/" + path,
        await installationToken(),
        method,
        body,
      ),
  };
}
