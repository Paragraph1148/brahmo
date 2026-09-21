// =================================================================
// GET /api/patients
// Returns: Patient[]  (the seeded demo patients, full records)
//
// The page used to read this straight from Supabase in the browser, which
// put the database credentials and the schema in the bundle. It now comes
// from the safety service, so the browser talks to one origin and knows
// nothing about the database.
// =================================================================
import { NextResponse } from "next/server";
import { errorResponse, get } from "@/lib/backend";

export async function GET() {
  try {
    return NextResponse.json(await get("/patients?detail=full"));
  } catch (err) {
    const { body, status } = errorResponse(err);
    return NextResponse.json(body, { status });
  }
}
