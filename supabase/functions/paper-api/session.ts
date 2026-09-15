export class SessionExpired extends Error {
  constructor() {
    super(
      "This temporary session has expired. Start a new live session to continue.",
    );
  }
}

/** Match the database's ten-minute retention even before its next cleanup. */
export function checkSession(rows: any[], tokenHash: string, now = Date.now()) {
  if (rows.length !== 1) throw new SessionExpired();
  if (tokenHash !== rows[0].token_hash) {
    throw Error(
      "This demonstration session is unavailable. Select Start afresh.",
    );
  }
  if (Date.parse(rows[0].touched_at) < now - 10 * 60 * 1000) {
    throw new SessionExpired();
  }
  return rows[0];
}

/** Cleanup can remove a session between authentication and paper_start. */
export async function startInSession(
  start: () => Promise<unknown>,
  validate: () => Promise<unknown>,
) {
  try {
    return await start();
  } catch (error) {
    try {
      await validate();
    } catch (sessionError) {
      if (sessionError instanceof SessionExpired) throw sessionError;
    }
    throw error;
  }
}
