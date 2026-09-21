// =================================================================
// POST /api/safety-check
// Body: { patient: Patient }   OR   { patient_id: number }
// Returns: SafetyReport
//
// Proxies to the Python safety service. The response shape is unchanged
// from when this route ran the TypeScript engine, with two additions the
// UI may ignore: `computed.eGFR_exact` (unrounded, what the CKD bands are
// read from) and `flags[].provenance`.
// =================================================================
import { NextResponse } from "next/server";
import { errorResponse, post } from "@/lib/backend";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const payload =
      body.patient !== undefined
        ? { patient: body.patient }
        : { patient_id: body.patient_id };
    return NextResponse.json(await post("/safety-check", payload));
  } catch (err) {
    const { body, status } = errorResponse(err);
    return NextResponse.json(body, { status });
  }
}
