"""Generate the online labelling page (an Artifact with a shared database).

    uv run python -m brahmo.ir.online -o /tmp/label-online.html

Same reading pass as :mod:`brahmo.ir.labeller`, but the grades live in the
artifact's database instead of the browser, so the pass can be done on a phone
in spare moments and read back here to commit. The local page remains for
working offline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brahmo.corpus import load_default
from brahmo.ir.harness import Campaign
from brahmo.ir.worksheet import build_pools

_PAGE = r"""<title>Guideline Reading Pass</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:ital,wght@0,400;0,500;1,400&display=swap">
<style>
  :root {
    color-scheme: light;
    --ground: #eef0f4;
    --surface: #ffffff;
    --sunk: #e3e7ee;
    --ink: #14171f;
    --muted: #5b6270;
    --line: #d4dae4;
    --accent: #2d4a7c;
    --yes: #1f6b45;
    --no: #a6392c;
    --flag: #8a5a12;
    --sans: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
    --serif: "IBM Plex Serif", ui-serif, Georgia, serif;
    --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --ground: #14161b; --surface: #1c1f26; --sunk: #23272f;
      --ink: #e8eaef; --muted: #99a0ad; --line: #2e333d;
      --accent: #8fb0dd; --yes: #5cba85; --no: #e08273; --flag: #d6a44e;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --ground: #14161b; --surface: #1c1f26; --sunk: #23272f;
    --ink: #e8eaef; --muted: #99a0ad; --line: #2e333d;
    --accent: #8fb0dd; --yes: #5cba85; --no: #e08273; --flag: #d6a44e;
  }

  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font-family: var(--sans); font-size: 16px; line-height: 1.55;
    -webkit-text-size-adjust: 100%;
  }
  .shell { min-height: 100%; display: flex; flex-direction: column; }
  .page { flex: 1; width: 100%; max-width: 620px; margin: 0 auto;
          padding-inline: 16px; padding-block: 14px 148px; }

  /* At phone width the heading wraps and the tally would sit over its second
     line, so the two stack and the count leads instead. */
  .top { display: flex; align-items: baseline; justify-content: space-between;
         gap: 10px; margin-bottom: 10px; }
  @media (max-width: 460px) {
    .top { flex-direction: column-reverse; align-items: flex-start; gap: 2px; }
  }
  .task { font-size: 15px; font-weight: 600; letter-spacing: -0.005em; margin: 0; }
  .tally { font-family: var(--mono); font-size: 12px; color: var(--muted);
           font-variant-numeric: tabular-nums; white-space: nowrap; }
  .track { height: 4px; background: var(--sunk); border-radius: 99px; overflow: hidden; }
  .track > i { display: block; height: 100%; background: var(--accent);
               transition: width .25s ease; }
  .sync { display: flex; align-items: center; gap: 6px; margin: 8px 0 20px;
          font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); flex: none; }
  .dot.ok { background: var(--yes); } .dot.busy { background: var(--flag); }
  .dot.off { background: var(--no); }

  .meta { font-family: var(--mono); font-size: 11px; color: var(--muted);
          letter-spacing: .02em; margin-bottom: 7px; }
  .ask { background: var(--surface); border: 1px solid var(--line);
         border-left: 3px solid var(--accent); border-radius: 3px;
         padding: 15px 17px; }
  .ask p { margin: 0; font-size: 17px; line-height: 1.45; text-wrap: pretty; }
  .who { font-size: 13px; color: var(--muted); margin: 9px 3px 0; line-height: 1.45; }

  .seam { display: flex; align-items: center; gap: 12px; margin: 22px 0 14px; }
  .seam::before, .seam::after { content: ""; height: 1px; background: var(--line); flex: 1; }
  .seam span { font-family: var(--mono); font-size: 10px; letter-spacing: .16em;
               text-transform: uppercase; color: var(--muted); }

  .doc { background: var(--surface); border: 1px solid var(--line);
         border-radius: 3px; padding: 17px 19px; }
  .cite { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-bottom: 9px; }
  .doc h2 { font-family: var(--sans); font-size: 15px; font-weight: 600;
            margin: 0 0 8px; letter-spacing: -0.004em; }
  .doc p { margin: 0; font-family: var(--serif); font-size: 16.5px;
           line-height: 1.6; text-wrap: pretty; }

  .bar { position: fixed; left: 0; right: 0; bottom: 0; background: var(--surface);
         border-top: 1px solid var(--line);
         padding: 10px 12px calc(10px + env(safe-area-inset-bottom, 0px)); }
  .bar .row { max-width: 620px; margin: 0 auto; display: grid; gap: 8px;
              grid-template-columns: 1fr 1.35fr; }
  .bar .row + .row { margin-top: 8px; grid-template-columns: 1.35fr 1fr; }
  button { font-family: var(--sans); font-size: 15px; font-weight: 500;
           border: 1px solid var(--line); background: var(--ground); color: var(--ink);
           border-radius: 3px; padding: 14px 10px; cursor: pointer; min-height: 48px;
           display: flex; align-items: center; justify-content: center; gap: 7px; }
  button:active { transform: translateY(1px); }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  button kbd { font-family: var(--mono); font-size: 10px; font-weight: 500;
               border: 1px solid currentColor; border-radius: 2px; padding: 1px 4px;
               opacity: .55; }
  .yes { color: var(--yes); border-color: color-mix(in srgb, var(--yes) 40%, var(--line)); }
  .no  { color: var(--no);  border-color: color-mix(in srgb, var(--no) 40%, var(--line)); }
  .flag{ color: var(--flag);border-color: color-mix(in srgb, var(--flag) 40%, var(--line)); }
  .ghost { color: var(--muted); }

  .card { background: var(--surface); border: 1px solid var(--line);
          border-radius: 3px; padding: 22px; }
  .card h2 { margin: 0 0 10px; font-size: 19px; letter-spacing: -0.01em; }
  .card p { margin: 0 0 12px; color: var(--muted); font-size: 14.5px; }
  .figures { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
             margin: 16px 0; }
  .fig { background: var(--sunk); border-radius: 3px; padding: 11px 12px; }
  .fig b { display: block; font-family: var(--mono); font-size: 20px; font-weight: 500;
           font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .fig span { font-size: 11px; color: var(--muted); text-transform: uppercase;
              letter-spacing: .06em; }
  .hint { font-size: 12.5px; color: var(--muted); line-height: 1.5; }
  .hint code { font-family: var(--mono); font-size: 11.5px; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="shell">
  <div class="page" id="page"></div>
</div>
<div class="bar" id="bar"></div>

<script>
const DATA = __DATA__;

const PAIRS = [];
for (const q of DATA.questions)
  for (const c of q.candidates) PAIRS.push({ qid: q.id, doc: c });

const Q_INDEX = new Map(DATA.questions.map((q, i) => [q.id, i]));

let grades = {};          // qid -> { docId: 0|1|2 }
let db = null;
let status = "local";     // local | syncing | synced | offline
let cursor = 0;
const pending = new Set();
const timers = new Map();

const LS = "brahmo-reading-pass-online-v1";
function readLocal() {
  try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch (e) { return {}; }
}
function writeLocal() {
  try { localStorage.setItem(LS, JSON.stringify(grades)); } catch (e) {}
}

const gradeOf = (p) => grades[p.qid]?.[p.doc];
const judged = () => PAIRS.filter((p) => gradeOf(p) !== undefined).length;
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function firstUnjudged() {
  const i = PAIRS.findIndex((p) => gradeOf(p) === undefined);
  return i < 0 ? PAIRS.length : i;
}

/* One document per question, written after a pause. 631 writes would be a
   burst the store is right to throttle; 44 documents flushed on a lull is the
   same information at a hundredth of the traffic. */
function scheduleFlush(qid) {
  pending.add(qid);
  clearTimeout(timers.get(qid));
  timers.set(qid, setTimeout(() => flush(qid), 700));
  setStatus("syncing");
}

async function flush(qid) {
  pending.delete(qid);
  if (!db) { setStatus(pending.size ? "syncing" : "local"); return; }
  try {
    await db.doc("grades/" + qid).set({
      question_id: qid,
      grades: grades[qid] || {},
      updated_at: new Date().toISOString(),
    });
    setStatus(pending.size ? "syncing" : "synced");
  } catch (e) {
    setStatus("offline");
  }
}

function setStatus(s) { status = s; paintStatus(); }

function paintStatus() {
  const el = document.getElementById("syncline");
  if (!el) return;
  const map = {
    local:   ["", "saved on this device only"],
    syncing: ["busy", "saving…"],
    synced:  ["ok", "saved — Claude can read this"],
    offline: ["off", "not syncing — progress kept on this device"],
  };
  const [cls, text] = map[status] || map.local;
  el.innerHTML = '<i class="dot ' + cls + '"></i><span>' + esc(text) + "</span>";
}

function grade(v) {
  if (cursor >= PAIRS.length) return;
  const p = PAIRS[cursor];
  (grades[p.qid] ||= {})[p.doc] = v;
  writeLocal();
  scheduleFlush(p.qid);
  cursor++;
  render();
}

function back() {
  if (cursor === 0) return;
  cursor--;
  const p = PAIRS[cursor];
  if (grades[p.qid]) { delete grades[p.qid][p.doc]; writeLocal(); scheduleFlush(p.qid); }
  render();
}

function render() {
  const page = document.getElementById("page");
  const bar = document.getElementById("bar");
  const done = judged();

  if (cursor >= PAIRS.length) {
    const flat = Object.values(grades).flatMap((g) => Object.values(g));
    const yes = flat.filter((g) => g > 0).length;
    const flagged = flat.filter((g) => g === 2).length;
    page.innerHTML =
      '<div class="card"><h2>Reading pass complete</h2>' +
      "<p>Every pooled candidate has a grade. Nothing else to do here — " +
      "tell Claude and it will read these out and commit them.</p>" +
      '<div class="figures">' +
      '<div class="fig"><b>' + done + "</b><span>judged</span></div>" +
      '<div class="fig"><b>' + yes + "</b><span>relevant</span></div>" +
      '<div class="fig"><b>' + flagged + "</b><span>flagged</span></div>" +
      "</div>" +
      '<p class="hint">The <b>flagged</b> ones are the grade-2 proposals. They stay ' +
      "marked as unconfirmed until a clinician looks at them — that part was " +
      "never yours to settle.</p>" +
      '<div class="sync" id="syncline"></div></div>';
    bar.innerHTML =
      '<div class="row" style="grid-template-columns:1fr">' +
      '<button class="ghost" onclick="back()"><kbd>U</kbd>Back one</button></div>';
    paintStatus();
    return;
  }

  const p = PAIRS[cursor];
  const q = DATA.questions[Q_INDEX.get(p.qid)];
  const d = DATA.documents[p.doc];
  const within = q.candidates.indexOf(p.doc) + 1;

  page.innerHTML =
    '<div class="top"><h1 class="task">Does this text answer this question?</h1>' +
    '<span class="tally">' + done + " / " + PAIRS.length + "</span></div>" +
    '<div class="track"><i style="width:' + (100 * done) / PAIRS.length + '%"></i></div>' +
    '<div class="sync" id="syncline"></div>' +
    '<div class="meta">question ' + (Q_INDEX.get(p.qid) + 1) + " of " + DATA.questions.length +
      " · candidate " + within + " of " + q.candidates.length +
      " · probes " + esc(q.probes) + "</div>" +
    '<div class="ask"><p>' + esc(q.question) + "</p></div>" +
    '<p class="who">' + esc(q.patient) + "</p>" +
    '<div class="seam"><span>against</span></div>' +
    '<div class="doc"><div class="cite">' + esc(p.doc) + " · " + esc(d.source) + "</div>" +
    "<h2>" + esc(d.title) + "</h2><p>" + esc(d.text) + "</p></div>";

  bar.innerHTML =
    '<div class="row">' +
    '<button class="no" onclick="grade(0)"><kbd>N</kbd>No</button>' +
    '<button class="yes" onclick="grade(1)"><kbd>Y</kbd>Yes, it answers it</button>' +
    "</div>" +
    '<div class="row">' +
    '<button class="flag" onclick="grade(2)"><kbd>E</kbd>Yes &amp; looks essential</button>' +
    '<button class="ghost" onclick="back()"><kbd>U</kbd>Back</button>' +
    "</div>";
  paintStatus();
}

addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "n" || k === "0") { e.preventDefault(); grade(0); }
  else if (k === "y" || k === "1") { e.preventDefault(); grade(1); }
  else if (k === "e" || k === "2") { e.preventDefault(); grade(2); }
  else if (k === "u" || k === "backspace") { e.preventDefault(); back(); }
});

/* Render from local state immediately; the store lights up when it answers. */
grades = readLocal();
cursor = firstUnjudged();
render();

(async () => {
  /* Optional chaining throughout: the namespace is absent when the page is
     opened from disk, and absence is a supported state, not an error. */
  const store = await window.claude?.use?.("db");
  if (!store) { setStatus("offline"); return; }
  db = store;
  try {
    const snap = await db.collection("grades").get();
    let merged = false;
    for (const doc of snap.docs) {
      const body = doc.data() || {};
      const stored = body.grades || {};
      const local = grades[doc.id] || {};
      /* The store wins where the two disagree: it is the record every device
         shares, and a stale phone should not undo a laptop. */
      grades[doc.id] = Object.assign({}, local, stored);
      if (Object.keys(stored).length) merged = true;
    }
    if (merged) { writeLocal(); cursor = firstUnjudged(); }
    setStatus(pending.size ? "syncing" : "synced");
    render();
  } catch (e) {
    setStatus("offline");
  }
})();
</script>
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
    parser.add_argument("-o", "--out", default="label-online.html")
    args = parser.parse_args()
    page = build_page()
    Path(args.out).write_text(page, encoding="utf-8")
    print(f"wrote {args.out} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
