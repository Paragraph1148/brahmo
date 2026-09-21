// =================================================================
// Export the seeded reference data as JSON for the Python port.
//
// The rows come from PGlite running this repository's own schema.sql and
// seed.sql, so the fixtures are the real data rather than a second copy of
// it maintained by hand. Regenerate with `npm run fixtures` whenever the
// seed changes.
// =================================================================
import "./harness/env.mjs";
import { bootstrapDb } from "./harness/db.mjs";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
mkdirSync(OUT, { recursive: true });

const pg = await bootstrapDb();
for (const [table, order] of [
  ["drugs", "id"],
  ["drug_interactions", "id"],
  ["indian_guidelines", "id"],
  ["patients", "id"],
  ["hospital_formulary", "id"],
] as const) {
  const res = await pg.query(`SELECT * FROM ${table} ORDER BY ${order}`);
  writeFileSync(join(OUT, `${table}.json`), JSON.stringify(res.rows, null, 2) + "\n");
  console.log(`${table.padEnd(20)} ${String(res.rows.length).padStart(4)} rows`);
}
