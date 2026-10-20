/** A known finish operation can be read only by its original authenticated runner. */
export async function finishReceipt(
  request: Request,
  id: string,
  operation: string,
  runner: (request: Request, id: string, finishing: boolean) => Promise<any>,
  db: (path: string, method: string, body: unknown) => Promise<any>,
) {
  if (
    request.method !== "GET" ||
    !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(operation)
  ) throw Error("Invalid finish receipt request.");
  await runner(request, id, true);
  // This read-only RPC uses POST for scalar arguments and one database attempt.
  // Ordinary GETs retain their existing database retry policy.
  const receipt = await db("rpc/paper_runner_finish_receipt", "POST", {
    p_request: id,
    p_operation: operation,
  });
  return { receipt };
}
