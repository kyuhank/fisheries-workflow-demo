# Hosted execution

The browser requests a fixed synthetic calculation from a Supabase Edge Function.
A private GitHub App starts `live.yml` in this repository. Its installation token
is restricted to this repository, with Actions write and Contents read permission;
no GitHub credential is returned to the visitor.

The standard GitHub runner downloads the image pinned in `live.yml`. The container
retrieves synthetic observations from PostgreSQL, executes `workflow/`, and saves
reports and a portable run bundle. The runner authenticates with GitHub OIDC;
the API verifies the repository, owner, workflow, branch, event, commit and run.
A reader's random session capability permits access only to that temporary session.
The API accepts supplied settings, not arbitrary commands, repositories or queries.

## Retention and limits

- Each session keeps its latest outputs and checkpoint. A subsequent run replaces
  the previous temporary execution record.
- PostgreSQL removes inactive sessions and their outputs after 10 minutes. Active
  calculations have an eight-minute deadline.
- `cleanup.yml` removes completed demo and cleanup runs older than 10 minutes.
  It runs twice an hour; GitHub may delay scheduled jobs. CI history and releases
  are outside this deletion rule. No site deployment or source commit is made
  when a reader runs the demonstration.
- The service allows three active executions, 20 temporary sessions and 300 runs
  a day. The hosting uses Supabase Free and public standard GitHub runners.
  No paid runner or service upgrade is enabled. Free-service limits or inactivity
  can make online execution unavailable; the downloaded offline modes remain usable.

## Hosting another copy

This service is specific to the paper repository. For a separate installation:

1. Create a Free Supabase project and apply `schema.sql` to its database.
2. Load the fixed records from `data/`; grant public users no table access.
3. Update repository IDs, project URL and callback URL in the server, runner and
   `config.json`. Deploy `supabase/functions/paper-api` with JWT verification
   disabled: the function performs its own session and OIDC checks.
4. Register a private GitHub App and install it on that repository only. The owner
   registration page exchanges its one-use manifest code server-side. App keys
   reside in `paper_app`, which is accessible only to the service role.
5. Test reader isolation, full and partial execution, cleanup and offline use
   before sharing the new address.

Changing the cloud provider does not require changing the scientific calculations.
A production service requires its own data-access controls and operational support.
