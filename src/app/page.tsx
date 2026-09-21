"use client";

import { useEffect, useState } from "react";
import type { Patient, SafetyReport, SafetyFlag } from "@/lib/types";

const SEVERITY_STYLES: Record<SafetyFlag["severity"], string> = {
  critical: "bg-red-50 border-red-300 text-red-900",
  warning: "bg-orange-50 border-orange-300 text-orange-900",
  caution: "bg-yellow-50 border-yellow-300 text-yellow-900",
  info: "bg-blue-50 border-blue-300 text-blue-900",
};

const SEVERITY_BADGE: Record<SafetyFlag["severity"], string> = {
  critical: "bg-red-600 text-white",
  warning: "bg-orange-500 text-white",
  caution: "bg-yellow-500 text-white",
  info: "bg-blue-500 text-white",
};

// Suggested clinical questions per patient (clinician dropdown in real use)
const SUGGESTED_QUESTIONS: Record<number, string[]> = {
  1: [
    "HbA1c is 8.4% on Metformin 2g. What second-line agent should I add?",
    "Patient wants to know the cheapest effective option. What would you suggest?",
  ],
  2: [
    "HbA1c is 9.2% on Metformin + Glimepiride. eGFR is 32. How should I transition this patient to insulin?",
    "Should I continue Metformin and Glimepiride at this eGFR?",
  ],
  3: [
    "Newly diagnosed T2DM. He's an auto-driver, no insurance, daily wage ₹800. What regimen?",
    "His ALT is 68 with NAFLD. Anything specifically beneficial?",
  ],
  4: [
    "STEMI just walked in — chest pain 2 hrs, anterior ST elevation. What's the immediate protocol?",
    "Cath lab is busy. Streptokinase or Tenecteplase?",
  ],
  5: [
    "Post-MI on DAPT, now new AF. CHA₂DS₂-VASc needs anticoagulation. How do I manage triple therapy?",
    "Which DOAC for this patient and for how long alongside DAPT?",
  ],
  6: [
    "HbA1c is 8.6% with HFrEF (EF 30%) and CKD 3a. How do I optimize her diabetes regimen?",
    "K+ is 5.1 on Ramipril + Spironolactone. Should I stop anything?",
  ],
};

type ClaudeResponse = {
  optionC: { prompt: string; response: string; meta: any };
  generic: { prompt: string; response: string };
  safety_report: SafetyReport;
};

export default function Home() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [report, setReport] = useState<SafetyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Phase 4 additions
  const [question, setQuestion] = useState("");
  const [claudeResult, setClaudeResult] = useState<ClaudeResponse | null>(null);
  const [claudeLoading, setClaudeLoading] = useState(false);
  const [showPromptInspector, setShowPromptInspector] = useState(false);

  useEffect(() => {
    (async () => {
      // Patients come from the safety service rather than straight from
      // Supabase: the browser no longer needs database credentials or any
      // knowledge of the schema.
      try {
        const res = await fetch("/api/patients");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Could not load patients");
        setPatients(data as Patient[]);
      } catch (e: any) {
        setError(e.message);
      }
    })();
  }, []);

  async function runCheck(id: number) {
    setSelectedId(id);
    setReport(null);
    setClaudeResult(null);
    setQuestion("");
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/safety-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patient_id: id }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Safety check failed");
      }
      const data = (await res.json()) as SafetyReport;
      setReport(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function runClaude() {
    if (!selectedId || !question.trim()) return;
    setClaudeResult(null);
    setError(null);
    setClaudeLoading(true);
    try {
      const res = await fetch("/api/claude", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patient_id: selectedId, question }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Claude API failed");
      }
      const data = (await res.json()) as ClaudeResponse;
      setClaudeResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setClaudeLoading(false);
    }
  }

  const selectedPatient = patients.find((p) => p.id === selectedId);
  const suggestions = selectedId ? SUGGESTED_QUESTIONS[selectedId] || [] : [];

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="mb-6 border-b border-slate-200 pb-4">
        <h1 className="text-2xl font-semibold text-slate-900">
          BRAHMO Clinical AI — India
        </h1>
        <p className="text-sm text-slate-600">
          Indian-context clinical decision support · Diabetes + Cardiovascular ·
          Apollo Chennai
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-red-800">
          {error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Patient selector */}
        <aside className="col-span-3">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Patients
          </h2>
          <div className="space-y-2">
            {patients.length === 0 && (
              <p className="text-sm text-slate-500">
                No patients loaded. Did you run seed.sql?
              </p>
            )}
            {patients.map((p) => (
              <button
                key={p.id}
                onClick={() => runCheck(p.id)}
                className={`block w-full rounded border p-3 text-left transition ${
                  selectedId === p.id
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="text-xs font-medium text-slate-500">
                  Patient {p.id}
                </div>
                <div className="text-sm font-semibold">{p.patient_label}</div>
                <div className="text-xs text-slate-600">
                  {p.age}
                  {p.sex} · BMI {p.bmi}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Main panel */}
        <section className="col-span-9">
          {!selectedPatient && (
            <div className="rounded border border-dashed border-slate-300 p-12 text-center text-slate-500">
              Select a patient to run safety checks
            </div>
          )}

          {selectedPatient && (
            <>
              <div className="mb-4 rounded border border-slate-200 bg-white p-4">
                <h2 className="text-lg font-semibold">
                  {selectedPatient.patient_label}
                </h2>
                <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
                  <div>
                    <span className="text-slate-500">Age/Sex:</span>{" "}
                    {selectedPatient.age}/{selectedPatient.sex}
                  </div>
                  <div>
                    <span className="text-slate-500">BMI:</span>{" "}
                    {selectedPatient.bmi}
                  </div>
                  <div>
                    <span className="text-slate-500">Insurance:</span>{" "}
                    {selectedPatient.insurance?.provider || "None"}
                  </div>
                </div>
                <div className="mt-3 text-sm">
                  <div className="text-slate-500">Conditions:</div>
                  <div>{selectedPatient.conditions.join(" · ")}</div>
                </div>
                <div className="mt-2 text-sm">
                  <div className="text-slate-500">Medications:</div>
                  <div>
                    {selectedPatient.medications.length === 0
                      ? "None"
                      : selectedPatient.medications
                          .map((m) => `${m.drug} ${m.dose}`)
                          .join(" · ")}
                  </div>
                </div>
                <div className="mt-2 text-sm">
                  <div className="text-slate-500">Allergies:</div>
                  <div>{selectedPatient.allergies.join(" · ")}</div>
                </div>
              </div>

              {loading && (
                <div className="rounded border border-slate-200 bg-white p-6 text-center text-slate-500">
                  Running safety checks…
                </div>
              )}

              {report && (
                <>
                  <div className="mb-4 grid grid-cols-3 gap-3">
                    <div className="rounded border border-slate-200 bg-white p-3">
                      <div className="text-xs uppercase text-slate-500">
                        eGFR
                      </div>
                      <div className="text-xl font-bold">
                        {report.computed.eGFR ?? "—"}
                      </div>
                      <div className="text-xs text-slate-600">
                        {report.computed.eGFR_stage}
                      </div>
                    </div>
                    <div className="rounded border border-slate-200 bg-white p-3">
                      <div className="text-xs uppercase text-slate-500">
                        CHA₂DS₂-VASc
                      </div>
                      <div className="text-xl font-bold">
                        {report.computed.chads_vasc ?? "—"}
                      </div>
                      <div className="text-xs text-slate-600">
                        {report.computed.chads_vasc !== null
                          ? "AF patient"
                          : "N/A"}
                      </div>
                    </div>
                    <div className="rounded border border-slate-200 bg-white p-3">
                      <div className="text-xs uppercase text-slate-500">
                        BMI Category
                      </div>
                      <div className="text-xl font-bold">
                        {report.computed.bmi_category}
                      </div>
                      <div className="text-xs text-slate-600">
                        Asian-Pacific cutoffs
                      </div>
                    </div>
                  </div>

                  <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Safety Alerts ({report.flags.length})
                  </h3>
                  <div className="space-y-2">
                    {report.flags.length === 0 && (
                      <div className="rounded border border-slate-200 bg-white p-4 text-sm text-slate-600">
                        No safety alerts — this patient is clinically
                        straightforward. The cost / lifestyle context shines in
                        the Option C response below.
                      </div>
                    )}
                    {report.flags.map((flag, i) => (
                      <div
                        key={i}
                        className={`rounded border p-3 ${SEVERITY_STYLES[flag.severity]}`}
                      >
                        <div className="flex items-start gap-3">
                          <span
                            className={`mt-0.5 rounded px-2 py-0.5 text-xs font-bold uppercase ${SEVERITY_BADGE[flag.severity]}`}
                          >
                            {flag.severity}
                          </span>
                          <div className="flex-1">
                            <div className="font-semibold">{flag.title}</div>
                            <div className="text-sm">{flag.detail}</div>
                            {flag.action && (
                              <div className="mt-1 text-sm">
                                <span className="font-semibold">Action: </span>
                                {flag.action}
                              </div>
                            )}
                            {flag.guideline_source && (
                              <div className="mt-1 text-xs italic">
                                Source: {flag.guideline_source}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {report.drugs_to_avoid.length > 0 && (
                    <>
                      <h3 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-slate-500">
                        Drugs to Avoid
                      </h3>
                      <ul className="list-disc space-y-1 pl-5 text-sm">
                        {report.drugs_to_avoid.map((d, i) => (
                          <li key={i}>
                            <span className="font-semibold">{d.drug}</span> —{" "}
                            {d.reason}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  {report.recommended_drug_classes.length > 0 && (
                    <>
                      <h3 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-slate-500">
                        Recommended Drug Classes
                      </h3>
                      <ul className="list-disc space-y-1 pl-5 text-sm">
                        {report.recommended_drug_classes.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    </>
                  )}

                  {/* =================================================== */}
                  {/* PHASE 4 — Ask Claude (Generic vs Option C)         */}
                  {/* =================================================== */}
                  <div className="mt-8 border-t border-slate-300 pt-6">
                    <h3 className="mb-3 text-base font-semibold text-slate-800">
                      Ask Claude — Generic vs Option C
                    </h3>
                    <div className="rounded border border-slate-200 bg-white p-4">
                      <label className="block text-xs font-semibold uppercase text-slate-500">
                        Clinical question
                      </label>
                      <textarea
                        className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
                        rows={2}
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder="e.g. What second-line agent should I add?"
                      />
                      {suggestions.length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs text-slate-500">
                            Suggested:
                          </div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {suggestions.map((s, i) => (
                              <button
                                key={i}
                                onClick={() => setQuestion(s)}
                                className="rounded border border-slate-300 bg-slate-50 px-2 py-1 text-xs hover:bg-slate-100"
                              >
                                {s.length > 60 ? s.slice(0, 60) + "…" : s}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="mt-3 flex items-center gap-3">
                        <button
                          onClick={runClaude}
                          disabled={!question.trim() || claudeLoading}
                          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300"
                        >
                          {claudeLoading ? "Running both prompts…" : "Run comparison"}
                        </button>
                        {claudeResult && (
                          <button
                            onClick={() => setShowPromptInspector((v) => !v)}
                            className="text-xs text-blue-600 underline"
                          >
                            {showPromptInspector ? "Hide" : "Inspect"} composed prompt
                          </button>
                        )}
                      </div>
                    </div>

                    {claudeResult && (
                      <>
                        {/* Meta badges */}
                        <div className="mt-4 flex flex-wrap gap-2 text-xs">
                          <span className="rounded bg-slate-200 px-2 py-1">
                            Condition tags:{" "}
                            {claudeResult.optionC.meta.condition_tags.join(", ")}
                          </span>
                          <span className="rounded bg-slate-200 px-2 py-1">
                            {claudeResult.optionC.meta.guidelines_count} guidelines pulled
                          </span>
                          <span className="rounded bg-slate-200 px-2 py-1">
                            {claudeResult.optionC.meta.drugs_count} drugs in context
                          </span>
                          {claudeResult.optionC.meta.active_sources.map((s: string) => (
                            <span
                              key={s}
                              className="rounded bg-green-100 px-2 py-1 text-green-800"
                            >
                              📖 {s}
                            </span>
                          ))}
                        </div>

                        {/* Side-by-side responses */}
                        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
                          <div className="rounded border-2 border-slate-300 bg-white">
                            <div className="border-b border-slate-300 bg-slate-100 px-3 py-2 text-sm font-semibold">
                              ⚪ Generic Claude (no India context)
                            </div>
                            <div className="whitespace-pre-wrap p-3 text-sm">
                              {claudeResult.generic.response}
                            </div>
                          </div>
                          <div className="rounded border-2 border-green-400 bg-white">
                            <div className="border-b border-green-400 bg-green-50 px-3 py-2 text-sm font-semibold text-green-900">
                              🟢 Option C (India context injected)
                            </div>
                            <div className="whitespace-pre-wrap p-3 text-sm">
                              {claudeResult.optionC.response}
                            </div>
                          </div>
                        </div>

                        {/* Prompt inspector */}
                        {showPromptInspector && (
                          <div className="mt-4 rounded border border-slate-300 bg-slate-50 p-3">
                            <div className="mb-2 text-xs font-semibold uppercase text-slate-600">
                              Option C composed prompt (sent to Claude)
                            </div>
                            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-white p-3 text-xs">
                              {claudeResult.optionC.prompt}
                            </pre>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
