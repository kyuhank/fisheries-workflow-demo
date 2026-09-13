import { createGitHub, REPOSITORY as REPO, WORKFLOW } from "./github.ts";
import { setup } from "./setup.ts";
const jobs = [
  "submission",
  "qc",
  "database",
  "extract",
  "cpue_a",
  "cpue_b",
  "cpue_summary",
  "cpue_report",
  "prepare_a",
  "prepare_b",
  "assessment_a1",
  "assessment_a2",
  "assessment_b1",
  "assessment_b2",
  "assessment_summary",
  "assessment_report",
];
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,Authorization",
  "Cache-Control": "no-store",
};
const reply = (value: unknown, status = 200) =>
  Response.json(value, { status, headers: cors });
const hash = async (s: string) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)),
    ),
  ).map((x) => x.toString(16).padStart(2, "0")).join("");
const uuid = (s: string) =>
  /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(s);
async function db(path: string, method = "GET", body?: unknown) {
  const r = await fetch(Deno.env.get("SUPABASE_URL") + "/rest/v1/" + path, {
    method,
    headers: {
      apikey: Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
      Authorization: "Bearer " + Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"),
      "Content-Type": "application/json",
      Prefer: "return=representation,resolution=merge-duplicates",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw Error("The database request could not be completed.");
  return r.status === 204 ? null : await r.json();
}
const connection = createGitHub(db);
const github = connection.request;
const bearer = (r: Request) =>
  r.headers.get("Authorization")?.replace(/^Bearer /, "") || "";
async function session(request: Request, id: string) {
  if (!uuid(id)) throw Error("Select a demonstration session.");
  const rows = await db(
    "paper_sessions?id=eq." + id + "&select=id,token_hash,state",
  );
  if (rows.length !== 1 || await hash(bearer(request)) !== rows[0].token_hash) {
    throw Error(
      "This demonstration session is unavailable. Select Start afresh.",
    );
  }
  return rows[0];
}
const bytes = (s: string) =>
  Uint8Array.from(
    atob(s.replace(/-/g, "+").replace(/_/g, "/")),
    (c) => c.charCodeAt(0),
  );
let jwks: any;
async function runner(request: Request, id: string) {
  if (!uuid(id)) throw Error("Invalid run.");
  const parts = bearer(request).split(".");
  if (parts.length !== 3) throw Error("Runner identity required.");
  const header = JSON.parse(new TextDecoder().decode(bytes(parts[0]))),
    claims = JSON.parse(new TextDecoder().decode(bytes(parts[1]))),
    now = Date.now() / 1000;
  if (header.alg !== "RS256") throw Error("Invalid signature.");
  if (!jwks || jwks.exp < now) {
    const r = await fetch(
      "https://token.actions.githubusercontent.com/.well-known/jwks",
    );
    if (!r.ok) throw Error("Runner verification unavailable.");
    jwks = { ...await r.json(), exp: now + 300 };
  }
  const jwk = jwks.keys.find((k: any) =>
    k.kid === header.kid && k.kty === "RSA"
  );
  if (!jwk) throw Error("Unknown signing key.");
  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  if (
    !await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      key,
      bytes(parts[2]),
      new TextEncoder().encode(parts[0] + "." + parts[1]),
    )
  ) throw Error("Invalid signature.");
  if (
    claims.iss !== "https://token.actions.githubusercontent.com" ||
    claims.aud !== "fisheries-paper-demo" || claims.repository !== REPO ||
    claims.repository_id !== "1367765865" ||
    claims.repository_owner_id !== "51262923" ||
    claims.ref !== "refs/heads/main" ||
    claims.event_name !== "workflow_dispatch" ||
    claims.workflow_ref !== REPO + "/" + WORKFLOW + "@refs/heads/main" ||
    claims.runner_environment !== "github-hosted" ||
    !Number.isFinite(claims.exp) || claims.exp <= now ||
    !Number.isFinite(claims.iat) || claims.iat < now - 600 ||
    claims.iat > now + 30 || !Number.isFinite(claims.nbf) ||
    claims.nbf > now + 30 || !/^\d{1,20}$/.test(claims.run_id || "")
  ) throw Error("Untrusted runner.");
  const rows = await db("paper_runs?id=eq." + id);
  if (rows.length !== 1) throw Error("Run expired.");
  const run = rows[0];
  if (run.commit_sha !== claims.sha) throw Error("Different code version.");
  if (run.github_run && run.github_run !== claims.run_id) {
    throw Error("Different run identity.");
  }
  if (!["queued", "running", "handover"].includes(run.status)) {
    throw Error("Run is no longer active.");
  }
  if (!run.github_run) {
    const remote = await github("actions/runs/" + claims.run_id);
    if (
      remote.path !== WORKFLOW || remote.head_sha !== run.commit_sha ||
      remote.head_sha !== claims.sha || !remote.display_title.endsWith(id)
    ) throw Error("Run does not match the request.");
    await db("paper_runs?id=eq." + id, "PATCH", {
      github_run: claims.run_id,
      status: "running",
    });
  }
  return { ...run, github_run: claims.run_id };
}
async function dataRows(year: number) {
  const sets = [];
  for (let offset = 0;; offset += 1000) {
    const rows = await db(
      "paper_sets?year=lte." + year + "&order=year,set_id&limit=1000&offset=" +
        offset,
    );
    sets.push(...rows);
    if (rows.length < 1000) break;
  }
  return {
    sets,
    catch: await db("paper_catches?year=lte." + year + "&order=year"),
  };
}

const observed = new Map<string, { at: number; remote: any }>();
async function observeRun(run: any) {
  const cached = observed.get(run.id);
  if (cached && Date.now() - cached.at < 5000) {
    return { ...run, ...cached.remote };
  }
  let remote;
  if (run.github_run) remote = await github("actions/runs/" + run.github_run);
  else {
    const list = await github(
      "actions/workflows/live.yml/runs?event=workflow_dispatch&per_page=30",
    );
    remote = list.workflow_runs.find((r: any) =>
      r.path === WORKFLOW && r.head_sha === run.commit_sha &&
      r.display_title.endsWith(run.id)
    );
  }
  const update: any = {};
  if (remote) {
    update.github_run = String(remote.id);
    if (remote.status === "completed" && remote.conclusion !== "success") {
      update.status = "failed";
      update.error = "The GitHub execution " + remote.conclusion +
        ". Open its execution record for details.";
    }
    // Never overwrite a completion saved by the runner during this network request.
    await db(
      "paper_runs?id=eq." + run.id + "&status=in.(queued,running,handover)",
      "PATCH",
      update,
    );
  }
  if (observed.size > 50) observed.clear();
  observed.set(run.id, { at: Date.now(), remote: update });
  return { ...run, ...update };
}
export async function handle(request: Request) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }
  const u = new URL(request.url),
    path = u.pathname.split("/paper-api")[1] || "/";
  try {
    if (path === "/info") {
      let configured = false;
      try {
        await connection.installationToken();
        configured = true;
      } catch { /* No credentials or errors exposed. */ }
      return reply({
        configured,
        repository: REPO,
        provider: "GitHub Actions + Supabase PostgreSQL",
      });
    }
    if (path.startsWith("/setup/") && request.method === "POST") {
      const text = await request.text();
      if (text.length > 1024) throw Error("Invalid setup request.");
      return reply(await setup(path, JSON.parse(text), db));
    }
    if (path === "/session" && request.method === "POST") {
      await db("rpc/paper_cleanup", "POST", {});
      const existing = await db("paper_sessions?select=id&limit=21");
      if (existing.length >= 20) {
        return reply({
          error:
            "The shared demo is busy. Use browser calculation or try later.",
        }, 429);
      }
      const id = crypto.randomUUID(),
        token = crypto.randomUUID() + crypto.randomUUID();
      await db("paper_sessions", "POST", { id, token_hash: await hash(token) });
      return reply({ id, token });
    }
    if (path.startsWith("/runner/")) {
      const id = u.searchParams.get("request") || "";
      const run = await runner(request, id);
      if (path === "/runner/context") {
        const [s] = await db("paper_sessions?id=eq." + run.session_id);
        return reply({ ...run, checkpoint: s.checkpoint });
      }
      if (path === "/runner/data") {
        return reply(await dataRows(run.settings.last_year));
      }
      if (path === "/runner/control") {
        return reply({
          transfer_count: run.transfer_count,
          connected: run.connected,
        });
      }
      if (request.method !== "POST") return reply({ error: "Use POST." }, 405);
      const text = await request.text();
      if (text.length > 16000000) throw Error("Output too large.");
      const body = JSON.parse(text);
      if (path === "/runner/event") {
        if (body.event.job && !jobs.includes(body.event.job)) {
          throw Error("Unknown job.");
        }
        await db("paper_events", "POST", { request_id: id, event: body.event });
        await db("paper_runs?id=eq." + id, "PATCH", {
          status: body.event.state === "handover" ? "handover" : "running",
        });
        if (body.output && jobs.includes(body.event.job)) {
          await db("paper_outputs", "POST", {
            session_id: run.session_id,
            job: body.event.job,
            output: body.output,
          });
        }
        if (body.state) {
          await db("paper_sessions?id=eq." + run.session_id, "PATCH", {
            state: body.state,
            touched_at: new Date().toISOString(),
          });
        }
        if (body.event.job === "database" && body.event.state === "complete") {
          await db("paper_sessions?id=eq." + run.session_id, "PATCH", {
            accepted_year: run.settings.last_year,
          });
        }
        return reply({ ok: true });
      }
      if (path === "/runner/finish") {
        await db("paper_sessions?id=eq." + run.session_id, "PATCH", {
          checkpoint: body.checkpoint,
          bundle: body.bundle,
          state: body.state,
          touched_at: new Date().toISOString(),
        });
        await db("paper_runs?id=eq." + id, "PATCH", {
          status: body.error ? "failed" : "complete",
          error: body.error || null,
          result: body.result || null,
        });
        return reply({ ok: true });
      }
      return reply({ error: "Unknown runner operation." }, 404);
    }
    const sid = u.searchParams.get("session") || "";
    const s = await session(request, sid);
    if (path === "/state") {
      const rows = await db(
        "paper_runs?session_id=eq." + sid + "&order=created_at.desc&limit=1",
      );
      let run = rows[0] || null;
      if (run && ["queued", "running", "handover"].includes(run.status)) {
        run = await observeRun(run);
      }
      const after = Number(u.searchParams.get("after") || 0);
      if (!Number.isSafeInteger(after) || after < 0) {
        throw Error("Invalid event cursor.");
      }
      const events = run
        ? await db(
          "paper_events?request_id=eq." + run.id + "&id=gt." + after +
            "&order=id&limit=100",
        )
        : [];
      return reply({ run, state: s.state, events });
    }
    if (path === "/output") {
      const job = u.searchParams.get("job") || "";
      if (!jobs.includes(job)) throw Error("Unknown job.");
      const rows = await db(
        "paper_outputs?session_id=eq." + sid + "&job=eq." + job,
      );
      if (!rows.length) throw Error("This output is not ready.");
      return reply(rows[0].output);
    }
    if (path === "/bundle") {
      const [full] = await db("paper_sessions?id=eq." + sid + "&select=bundle");
      if (!full.bundle) throw Error("The result bundle is not ready.");
      return reply(full);
    }
    if (path === "/checkpoint") {
      const [full] = await db(
        "paper_sessions?id=eq." + sid + "&select=checkpoint",
      );
      return reply(full);
    }
    if (request.method !== "POST") return reply({ error: "Use POST." }, 405);
    const text = await request.text();
    if (text.length > 2048) throw Error("Request too large.");
    const b = JSON.parse(text);
    if (path === "/run") {
      await connection.installationToken();
      if (
        !jobs.includes(b.start) ||
        !["connected", "manual"].includes(b.handover) || !b.settings ||
        Object.keys(b).sort().join(",") !== "handover,settings,start" ||
        Object.keys(b.settings).sort().join(",") !==
          "last_year,min_hooks_a,mortality_2" ||
        ![2021, 2022, 2023, 2024].includes(b.settings.last_year) ||
        ![0, 1200].includes(b.settings.min_hooks_a) ||
        ![.25, .30, .35].includes(b.settings.mortality_2)
      ) throw Error("Select the supplied demonstration settings.");
      const id = crypto.randomUUID();
      const head = await github("commits/main");
      await db("rpc/paper_start", "POST", {
        p_session: sid,
        p_request: id,
        p_start: b.start,
        p_settings: b.settings,
        p_handover: b.handover,
      });
      await db("paper_runs?id=eq." + id, "PATCH", { commit_sha: head.sha });
      try {
        await github("actions/workflows/live.yml/dispatches", "POST", {
          ref: "main",
          inputs: { request_id: id },
        });
      } catch (e) {
        await db("paper_runs?id=eq." + id, "PATCH", {
          status: "failed",
          error: "GitHub dispatch failed.",
        });
        throw e;
      }
      return reply({ id, status: "queued" });
    }
    if (path === "/transfer") {
      const rows = await db(
        "paper_runs?session_id=eq." + sid + "&status=eq.handover",
      );
      if (rows.length !== 1) throw Error("No transfer is pending.");
      await db("paper_runs?id=eq." + rows[0].id, "PATCH", {
        transfer_count: rows[0].transfer_count + 1,
        connected: b.connect === true,
        status: "running",
      });
      return reply({ ok: true });
    }
    if (path === "/reset") {
      const active = await db(
        "paper_runs?session_id=eq." + sid +
          "&status=in.(queued,running,handover)",
      );
      if (active.length) throw Error("Wait for the current run.");
      await db("paper_runs?session_id=eq." + sid, "DELETE");
      await db("paper_outputs?session_id=eq." + sid, "DELETE");
      await db("paper_sessions?id=eq." + sid, "PATCH", {
        state: null,
        checkpoint: null,
        bundle: null,
        accepted_year: null,
      });
      return reply({ records: {} });
    }
    return reply({ error: "Unknown operation." }, 404);
  } catch (e) {
    return reply(
      { error: e instanceof Error ? e.message : "Request failed." },
      400,
    );
  }
}
if (import.meta.main) Deno.serve(handle);
