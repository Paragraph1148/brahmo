"""A local page for doing the reading pass.

    uv run python -m brahmo.ir.labeller -o ../docs/label.html

Self-contained: the questions, the pooled candidates and the patient summaries
are all baked into the file, so it opens straight from disk with no server and
nothing leaving the machine. Progress is kept in the browser and the finished
grades come back out as JSON to merge into the judgment set.

The tier the page asks for is the one a careful reader can settle — does this
text answer this question — with a separate key for flagging a candidate as
clinically essential, which stays marked as a proposal until a clinician sees
it. See :mod:`brahmo.ir.judgments` for why the two are kept apart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brahmo.corpus import load_default
from brahmo.ir.harness import Campaign
from brahmo.ir.worksheet import build_pools

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relevance reading pass</title>
<style>
  :root {
    --bg: #fbfaf8; --panel: #fff; --ink: #1d1b19; --muted: #6b6560;
    --line: #e5e0d8; --accent: #3b6ea5; --yes: #2f7a4f; --no: #a33a2e;
    --flag: #9a6a1f; --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.04);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #17161a; --panel: #201f24; --ink: #ece9e4; --muted: #9b948c;
      --line: #322f38; --accent: #7aa7d6; --yes: #5fbf87; --no: #e0796a;
      --flag: #d9a648; --shadow: 0 1px 2px rgba(0,0,0,.4);
    }
  }
  :root[data-theme="dark"] {
    --bg: #17161a; --panel: #201f24; --ink: #ece9e4; --muted: #9b948c;
    --line: #322f38; --accent: #7aa7d6; --yes: #5fbf87; --no: #e0796a;
    --flag: #d9a648; --shadow: 0 1px 2px rgba(0,0,0,.4);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.6 ui-serif, Georgia, "Times New Roman", serif;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 720px; margin: 0 auto; padding: 24px 16px 96px; }
  header { display: flex; justify-content: space-between; align-items: baseline;
           gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
  h1 { font-size: 19px; margin: 0; font-weight: 600; letter-spacing: -0.01em; }
  .count { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--muted); }
  .bar { height: 3px; background: var(--line); border-radius: 2px; overflow: hidden; margin-bottom: 26px; }
  .bar > i { display: block; height: 100%; background: var(--accent); transition: width .2s; }
  .ctx { font-size: 13px; color: var(--muted); margin-bottom: 6px;
         font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .q { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent);
       border-radius: 6px; padding: 14px 16px; margin-bottom: 8px; box-shadow: var(--shadow); }
  .q p { margin: 0; font-size: 17px; }
  .patient { font-size: 13px; color: var(--muted); margin: 8px 2px 20px; }
  .vs { text-align: center; color: var(--muted); font-size: 12px; letter-spacing: .14em;
        text-transform: uppercase; margin: 18px 0; }
  .doc { background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
         padding: 16px 18px; box-shadow: var(--shadow); }
  .doc .src { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
              color: var(--muted); margin-bottom: 8px; }
  .doc h2 { font-size: 16px; margin: 0 0 8px; font-weight: 600; }
  .doc p { margin: 0; }
  .keys { position: fixed; left: 0; right: 0; bottom: 0; background: var(--panel);
          border-top: 1px solid var(--line); padding: 10px 16px; display: flex;
          gap: 8px; justify-content: center; flex-wrap: wrap; }
  button { font: 500 14px/1 ui-sans-serif, system-ui, sans-serif; cursor: pointer;
           border: 1px solid var(--line); background: var(--bg); color: var(--ink);
           border-radius: 6px; padding: 9px 14px; }
  button:hover { border-color: var(--accent); }
  button kbd { font: 600 11px ui-monospace, monospace; opacity: .65; margin-right: 6px; }
  .b-yes { border-color: var(--yes); color: var(--yes); }
  .b-no  { border-color: var(--no);  color: var(--no); }
  .b-fl  { border-color: var(--flag); color: var(--flag); }
  .done { text-align: center; padding: 40px 0; }
  .done h2 { font-size: 22px; margin: 0 0 10px; }
  .note { font-size: 13px; color: var(--muted); max-width: 52ch; margin: 14px auto; }
  pre { background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
        padding: 12px; overflow: auto; font-size: 12px; max-height: 220px; text-align: left; }
  a { color: var(--accent); }
  @media (max-width: 480px) { .wrap { padding: 16px 16px 120px; } }
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<div class="keys" id="keys"></div>
<script>
const DATA = __DATA__;
const KEY = "brahmo-reading-pass-v1";

const pairs = [];
for (const q of DATA.questions)
  for (const c of q.candidates) pairs.push({ qid: q.id, doc: c });

let grades = {};
try { grades = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { grades = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(grades)); } catch (e) {} };
const id = (p) => p.qid + "|" + p.doc;

let i = pairs.findIndex((p) => grades[id(p)] === undefined);
if (i < 0) i = pairs.length;

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function grade(v) {
  if (i >= pairs.length) return;
  grades[id(pairs[i])] = v;
  save(); i++; render();
}
function undo() { if (i > 0) { i--; delete grades[id(pairs[i])]; save(); render(); } }

function exportJson() {
  const out = { schema: 1, corpus: "guidelines", reviewed: false,
    reading_pass_complete: pairs.every((p) => grades[id(p)] !== undefined),
    about: ["Reading pass output. Grade 1 = the text answers the question, settled by",
            "reading. Grade 2 = flagged as clinically essential by a non-clinician and",
            "NOT yet confirmed; treat as a 1 with a question mark until a clinician sees it."],
    queries: DATA.questions.map((q) => ({
      id: q.id, patient_id: q.patient_id, question: q.question, probes: q.probes,
      rationale: "",
      judgments: Object.fromEntries(
        q.candidates.map((d) => [d, grades[q.id + "|" + d] || 0]).filter(([, g]) => g > 0)),
    })),
  };
  const blob = new Blob([JSON.stringify(out, null, 2) + "\\n"], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "judgments-reading-pass.json"; a.click();
}

function render() {
  const app = document.getElementById("app"), keys = document.getElementById("keys");
  const done = pairs.filter((p) => grades[id(p)] !== undefined).length;

  if (i >= pairs.length) {
    const yes = Object.values(grades).filter((g) => g > 0).length;
    const flagged = Object.values(grades).filter((g) => g === 2).length;
    app.innerHTML = `<div class="done"><h2>Reading pass complete</h2>
      <p class="count">${pairs.length} judged · ${yes} relevant · ${flagged} flagged for a clinician</p>
      <p class="note">Download the file and merge it into
      <code>backend/src/brahmo/ir/data/judgments.json</code>. The flagged ones are
      proposals, not clinical judgments — they stay marked until a clinician confirms them.</p></div>`;
    keys.innerHTML = `<button onclick="exportJson()"><kbd>E</kbd>Download JSON</button>
      <button onclick="undo()"><kbd>U</kbd>Back one</button>`;
    return;
  }

  const p = pairs[i];
  const q = DATA.questions.find((x) => x.id === p.qid);
  const d = DATA.documents[p.doc];
  app.innerHTML = `
    <header><h1>Does this text answer this question?</h1>
      <span class="count">${done} / ${pairs.length}</span></header>
    <div class="bar"><i style="width:${(100 * done) / pairs.length}%"></i></div>
    <div class="ctx">${esc(q.id)} · probes: ${esc(q.probes)}</div>
    <div class="q"><p>${esc(q.question)}</p></div>
    <div class="patient">${esc(q.patient)}</div>
    <div class="vs">against</div>
    <div class="doc"><div class="src">${esc(p.doc)} · ${esc(d.source)}</div>
      <h2>${esc(d.title)}</h2><p>${esc(d.text)}</p></div>`;
  keys.innerHTML = `
    <button class="b-no"  onclick="grade(0)"><kbd>N</kbd>No</button>
    <button class="b-yes" onclick="grade(1)"><kbd>Y</kbd>Yes, it answers it</button>
    <button class="b-fl"  onclick="grade(2)"><kbd>E</kbd>Yes &amp; looks essential</button>
    <button onclick="undo()"><kbd>U</kbd>Back</button>`;
}

addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "n" || k === "0") { e.preventDefault(); grade(0); }
  else if (k === "y" || k === "1") { e.preventDefault(); grade(1); }
  else if (k === "e" || k === "2") { e.preventDefault(); i >= pairs.length ? exportJson() : grade(2); }
  else if (k === "u" || k === "backspace") { e.preventDefault(); undo(); }
});

render();
</script>
</body>
</html>
"""


def build_page() -> str:
    campaign = Campaign.build()
    corpus = load_default()
    pools = build_pools(depth=8)

    documents = {
        d.id: {
            "title": d.title,
            "text": d.text,
            "source": f"{d.source} {d.year}" if d.source else "—",
        }
        for d in campaign.store
    }

    questions = []
    for pool in pools:
        patient = corpus.patient(pool.question.patient_id)
        summary = "—"
        if patient:
            meds = ", ".join(m.drug for m in patient.medications) or "no medications"
            summary = (
                f"Patient {patient.id} · {patient.age:g}{patient.sex} · "
                f"{'; '.join(patient.conditions)} · on {meds}"
            )
        questions.append(
            {
                "id": pool.question.id,
                "patient_id": pool.question.patient_id,
                "question": pool.question.question,
                "probes": pool.question.probes,
                "patient": summary,
                "candidates": list(pool.candidates),
            }
        )

    payload = {"documents": documents, "questions": questions}
    return _PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", default="label.html")
    args = parser.parse_args()

    page = build_page()
    Path(args.out).write_text(page, encoding="utf-8")

    pairs = sum(len(q["candidates"]) for q in json.loads(
        page.split("const DATA = ", 1)[1].split(";\nconst KEY", 1)[0]
    )["questions"])
    print(f"wrote {args.out}")
    print(f"  {pairs} decisions, roughly {pairs * 6 // 60} minutes at 6s each")
    print("  open it in a browser; progress is kept locally and nothing is uploaded")


if __name__ == "__main__":
    main()
