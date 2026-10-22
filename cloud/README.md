# Hosted execution

The browser requests a small public-data calculation from a Supabase Edge Function.
A private GitHub App starts `live.yml` in this repository. Its installation token
is restricted to this repository, with Actions write and Contents read permission;
no GitHub credential is returned to the visitor.

The GitHub runner retrieves the pinned analysis repositories and starts the host R
coordinator. Each job runs its component’s Makefile in its assigned immutable image.
The coordinator retrieves the preserved WCPFC projection from PostgreSQL and saves
results, execution records and a portable run bundle. The runner authenticates with GitHub OIDC;
the API verifies the repository, owner, workflow, branch, event, commit and run.
A reader's random session capability permits access only to that temporary session.
The API accepts supplied settings, not arbitrary commands, repositories or queries.

## Retention and limits

- Each session keeps its latest outputs and checkpoint. A subsequent run replaces
  the previous temporary execution record.
- PostgreSQL removes inactive sessions and their outputs after 10 minutes. Active
  calculations have an eight-minute deadline. Running again after expiry opens
  a fresh session with the selected job and settings, rebuilding missing inputs.
  An uncertain dispatch response is never automatically repeated.
- `cleanup.yml` removes completed demo and cleanup runs older than 10 minutes.
  It runs twice an hour; GitHub may delay scheduled jobs. CI history and releases
  are outside this deletion rule. No site deployment or source commit is made
  when a reader runs the demonstration.
- The service allows three active executions, 20 temporary sessions and 300 runs
  a day. The hosting uses Supabase Free and public standard GitHub runners.
  No paid runner or service upgrade is enabled. Free-service limits or inactivity
  can interrupt online execution. Downloaded results remain readable.
- The atomic completion RPC has a 45-second SQL limit and a transaction-scoped
  16 MB `work_mem` setting. This is not a total memory limit. The API makes one
  database attempt with a 50-second deadline; the R runner checks the original
  receipt before retrying an uncertain completion. Other RPCs keep their existing
  limits. Run downloads require completed publication and a recorded archive.

## Hosting another copy

The service is configured for this demonstration repository. To host another copy:

1. Create a Free Supabase project and apply `schema.sql` to its database.
2. Apply `public-data.sql`. Run `python3 scripts/seed-public-data.py` and apply
   its `public-data-seed.sql` to load the checked records from `data/`.
   Grant public users no table access. The runner checks database rows and source
   identity against the preserved snapshot before calculation.
3. Update repository IDs, project URL and callback URL in the server, runner and
   `config.json`. Deploy `supabase/functions/paper-api` with JWT verification
   disabled: the function performs its own session and OIDC checks.
4. Register a private GitHub App and install it on that repository only. The owner
   registration page exchanges its one-use manifest code server-side. App keys
   reside in `paper_app`, which is accessible only to the service role.
5. Test reader isolation, full and partial execution, cleanup and saved-result viewing
   before sharing the new address.

Changing the cloud provider does not require changing the scientific calculations.
A production service requires its own data-access controls and operational support.

The paper project is `gvunwnpsfmylmqfqowzp`; the new inputs use only
`paper_public_sources`, `paper_public_sets` and `paper_public_catches`.
The workshop presentation links use separate repositories and the project
`tgusnkwvfzwdeufzevhk`. Do not apply these migrations or deploy `paper-api` there.
[Source links, units and the selection query](../data/public/README.md) remain
publicly inspectable without a database account.
