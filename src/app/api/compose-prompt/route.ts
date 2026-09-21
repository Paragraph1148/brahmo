// =================================================================
// POST /api/compose-prompt
// Body: { patient_id: number, question: string }
//   - Optional: { patient: Patient, ... } to skip the lookup
//
// Returns: { optionC, generic, meta, safety_report }
//
// Composes the prompts WITHOUT calling a model, for inspecting what the
// model would be given. Proxies to the Python service, which reaches no
// network on this path.
// =================================================================
import { NextResponse } from "next/server";
import { errorResponse, post } from "@/lib/backend";

type Composed = {
  report: unknown;
  optionC: string;
  generic: string;
  meta: unknown;
};

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const question = (body.question ?? "").toString().trim();
    if (!question) {
      return NextResponse.json({ error: "Provide a clinical `question`" }, { status: 400 });
    }

    const composed = await post<Composed>("/compose-prompt", {
      ...(body.patient !== undefined
        ? { patient: body.patient }
        : { patient_id: body.patient_id }),
      question,
    });

    // The service names it `report`; this route's long-standing contract
    // calls it `safety_report`. Renamed here so the UI is untouched.
    return NextResponse.json({
      optionC: composed.optionC,
      generic: composed.generic,
      meta: composed.meta,
      safety_report: composed.report,
    });
  } catch (err) {
    const { body, status } = errorResponse(err);
    return NextResponse.json(body, { status });
  }
}
