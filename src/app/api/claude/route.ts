// =================================================================
// POST /api/claude
// Body: { patient_id: number, question: string }
//
// Returns: {
//   optionC:  { prompt, response, meta },
//   generic:  { prompt, response },
//   safety_report
// }
//
// Calls the LLM TWICE in parallel:
//   1. Generic baseline (no India context) — proves the contrast
//   2. Option C with full India-injected context
//
// The safety report and both prompts come from the Python service, which
// settles every clinical decision before this route touches a model. The
// model call itself stays here: the Groq SDK and the API key already live
// in this process, and moving them would duplicate key handling for no
// gain. The ordering guarantee is unaffected — by the time `callLLM` runs,
// the verdict is already computed and is returned whether or not the model
// answers.
//
// The route path is kept as `/api/claude` so the rest of the app doesn't
// need to change. To swap providers, replace the Groq client below.
// =================================================================
import { NextResponse } from "next/server";
import { Groq } from "groq-sdk";
import { errorResponse, post } from "@/lib/backend";

const apiKey = process.env.GROQ_API_KEY;
const groq = apiKey ? new Groq({ apiKey }) : null;

const MODEL = "llama-3.3-70b-versatile";
const MAX_TOKENS = 2200;

async function callLLM(prompt: string): Promise<string> {
  if (!groq) {
    throw new Error(
      "GROQ_API_KEY is not set. Add it to .env.local (get one free at https://console.groq.com/keys) and restart the dev server.",
    );
  }

  const completion = await groq.chat.completions.create({
    model: MODEL,
    messages: [{ role: "user", content: prompt }],
    temperature: 0.3, // lower temp for clinical content
    max_tokens: MAX_TOKENS,
    top_p: 1,
    stream: false,
  });

  return completion.choices[0]?.message?.content || "";
}

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

    // 1. Safety engine + 2. both prompts, settled before any model call.
    const prompts = await post<Composed>("/compose-prompt", {
      ...(body.patient !== undefined
        ? { patient: body.patient }
        : { patient_id: body.patient_id }),
      question,
    });

    // 3. Call the LLM in parallel for both arms.
    const [genericResp, optionCResp] = await Promise.all([
      callLLM(prompts.generic),
      callLLM(prompts.optionC),
    ]);

    return NextResponse.json({
      optionC: {
        prompt: prompts.optionC,
        response: optionCResp,
        meta: prompts.meta,
      },
      generic: {
        prompt: prompts.generic,
        response: genericResp,
      },
      safety_report: prompts.report,
    });
  } catch (err) {
    const { body, status } = errorResponse(err);
    return NextResponse.json(body, { status });
  }
}
