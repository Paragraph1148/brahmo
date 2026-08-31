// =================================================================
// Hard network guard.
//
// The architectural claim under test is that the safety path is
// decided before any model is consulted. This asserts it mechanically:
// every outbound socket and fetch is intercepted and recorded, and the
// tests fail if the safety path opens even one.
// =================================================================
import http from "node:http";
import https from "node:https";
import net from "node:net";

export const outbound: string[] = [];

export function armNetworkGuard() {
  const record = (what: string) => {
    outbound.push(what);
    throw new Error(`[no-network] blocked outbound call: ${what}`);
  };

  globalThis.fetch = (async (input: any) => {
    record(`fetch ${typeof input === "string" ? input : input?.url ?? "?"}`);
  }) as typeof fetch;

  for (const [name, mod] of [["http", http], ["https", https]] as const) {
    (mod as any).request = (...a: any[]) => record(`${name}.request ${JSON.stringify(a[0])}`);
    (mod as any).get = (...a: any[]) => record(`${name}.get ${JSON.stringify(a[0])}`);
  }
  (net as any).connect = (...a: any[]) => record(`net.connect ${JSON.stringify(a[0])}`);
}

export function outboundCount() {
  return outbound.length;
}
