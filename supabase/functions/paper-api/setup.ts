/** Single-use owner registration. Reviewers never enter this flow. */
import { githubApi, OWNER_ID, PERMISSIONS, REPOSITORY } from "./github.ts";

const SITE = "https://kyuhank.github.io/fisheries-workflow-demo/";
const hash = async (value: string) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  ).map((n) => n.toString(16).padStart(2, "0")).join("");

export async function setup(path: string, body: any, db: any) {
  if (!/^[a-f0-9]{64}$/.test(body.state || "")) {
    throw Error("The owner setup link is invalid.");
  }
  const [record] = await db(
    "paper_app?id=eq.true&select=app_id,setup_hash,setup_expires",
  );
  if (
    !record || record.app_id || record.setup_hash !== await hash(body.state) ||
    Date.parse(record.setup_expires) <= Date.now()
  ) throw Error("The owner setup link has expired or was already used.");
  if (path === "/setup/manifest") {
    return {
      manifest: {
        name: "Fisheries paper demo",
        url: SITE,
        description: "Runs the synthetic fisheries workflow demonstration.",
        redirect_url: SITE + "setup.html",
        setup_url: SITE + "setup.html?installed=1",
        public: false,
        request_oauth_on_install: false,
        default_permissions: PERMISSIONS,
        default_events: [],
        hook_attributes: { active: false, url: SITE },
      },
    };
  }
  if (
    path !== "/setup/complete" || !/^[a-f0-9]{20,128}$/.test(body.code || "")
  ) throw Error("Invalid app registration.");
  const app = await githubApi(
    "app-manifests/" + body.code + "/conversions",
    undefined,
    "POST",
  );
  if (
    app.owner?.id !== OWNER_ID || !Number.isSafeInteger(app.id) || !app.pem ||
    !/^[a-z0-9-]+$/.test(app.slug) ||
    app.permissions?.actions !== "write" ||
    app.permissions?.contents !== "read" ||
    Object.keys(app.permissions).some((key) =>
      !["metadata", "actions", "contents"].includes(key)
    )
  ) {
    throw Error(
      "Register the app in the repository owner account with only the supplied permissions.",
    );
  }
  // Conditional update makes the registration one-use, including concurrent callbacks.
  const updated = await db(
    "paper_app?id=eq.true&app_id=is.null&setup_hash=eq." + record.setup_hash,
    "PATCH",
    {
      app_id: app.id,
      private_key: app.pem,
      slug: app.slug,
      setup_hash: null,
      setup_expires: null,
    },
  );
  if (updated.length !== 1) {
    throw Error("This registration was already completed.");
  }
  return {
    install_url: "https://github.com/apps/" + app.slug + "/installations/new",
    repository: REPOSITORY,
  };
}
