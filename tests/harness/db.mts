// =================================================================
// BRAHMO test harness — real Postgres, real schema, real seed.
//
// PGlite is Postgres compiled to WASM. We run the repository's own
// supabase/schema.sql and supabase/seed.sql against it verbatim, so
// the JSONB containment operators and the guidelines_for_condition /
// drugs_for_condition SQL functions are genuinely exercised.
//
// The only substitution is transport: `supabase.from` / `supabase.rpc`
// normally speak PostgREST over HTTP. Here they run the equivalent SQL
// in-process. src/lib/safety-engine.ts and src/lib/prompt-composer.ts
// are imported unmodified.
// =================================================================
import { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

export interface DbResult<T> {
  data: T | null;
  error: { message: string } | null;
}

let db: PGlite | null = null;

export async function bootstrapDb(): Promise<PGlite> {
  if (db) return db;
  const pg = new PGlite();

  // Supabase provides these roles; schema.sql GRANTs to them.
  await pg.exec(`CREATE ROLE anon; CREATE ROLE authenticated;`);

  // The only edit made to schema.sql: pgcrypto is not in PGlite's base build.
  // No column in this schema uses it (no gen_random_uuid / crypt), so dropping
  // the CREATE EXTENSION line changes nothing that the tests observe.
  const schema = readFileSync(join(ROOT, "supabase", "schema.sql"), "utf8").replace(
    /CREATE EXTENSION IF NOT EXISTS "pgcrypto";/,
    "-- [harness] pgcrypto omitted: unavailable in PGlite, unused by this schema"
  );
  const seed = readFileSync(join(ROOT, "supabase", "seed.sql"), "utf8");
  await pg.exec(schema);
  await pg.exec(seed);

  db = pg;
  return pg;
}

// -----------------------------------------------------------------
// PostgREST filter translation
// -----------------------------------------------------------------
function quote(v: unknown): string {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "TRUE" : "FALSE";
  return `'${String(v).replace(/'/g, "''")}'`;
}

/** Parses one PostgREST filter term, e.g. `drug_a_id.in.(1,2,3)` or `id.eq.4`. */
function parseTerm(term: string): string {
  const inMatch = term.match(/^([a-z_0-9]+)\.in\.\((.*)\)$/i);
  if (inMatch) {
    const [, col, list] = inMatch;
    if (list.trim() === "") return "FALSE";
    return `${col} IN (${list})`;
  }
  const opMatch = term.match(/^([a-z_0-9]+)\.(eq|neq|gt|gte|lt|lte)\.(.*)$/i);
  if (opMatch) {
    const [, col, op, val] = opMatch;
    const sqlOp = { eq: "=", neq: "<>", gt: ">", gte: ">=", lt: "<", lte: "<=" }[op.toLowerCase()]!;
    return `${col} ${sqlOp} ${quote(val)}`;
  }
  throw new Error(`harness: unsupported PostgREST filter term "${term}"`);
}

/** Splits an `.or()` argument on top-level commas (parens protect the IN lists). */
function splitTopLevel(s: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let cur = "";
  for (const ch of s) {
    if (ch === "(") depth++;
    if (ch === ")") depth--;
    if (ch === "," && depth === 0) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur) out.push(cur);
  return out;
}

class QueryBuilder<T> implements PromiseLike<DbResult<T[]>> {
  private wheres: string[] = [];
  private isSingle = false;

  constructor(private pg: PGlite, private table: string) {}

  select(_cols = "*") {
    return this;
  }

  or(expr: string) {
    const parts = splitTopLevel(expr).map(parseTerm);
    this.wheres.push(`(${parts.join(" OR ")})`);
    return this;
  }

  in(col: string, values: (string | number)[]) {
    this.wheres.push(values.length === 0 ? "FALSE" : `${col} IN (${values.map(quote).join(",")})`);
    return this;
  }

  eq(col: string, value: unknown) {
    this.wheres.push(`${col} = ${quote(value)}`);
    return this;
  }

  single(): PromiseLike<DbResult<T>> {
    this.isSingle = true;
    return this as unknown as PromiseLike<DbResult<T>>;
  }

  private sql(): string {
    const where = this.wheres.length ? ` WHERE ${this.wheres.join(" AND ")}` : "";
    return `SELECT * FROM ${this.table}${where}`;
  }

  async then<R1, R2 = never>(
    onfulfilled?: ((v: any) => R1 | PromiseLike<R1>) | null,
    onrejected?: ((r: any) => R2 | PromiseLike<R2>) | null
  ): Promise<R1 | R2> {
    let result: any;
    try {
      const res = await this.pg.query<T>(this.sql());
      queryCount++;
      if (this.isSingle) {
        result =
          res.rows.length === 1
            ? { data: res.rows[0], error: null }
            : { data: null, error: { message: `expected 1 row, got ${res.rows.length}` } };
      } else {
        result = { data: res.rows, error: null };
      }
    } catch (e: any) {
      result = { data: null, error: { message: e?.message ?? String(e) } };
    }
    return onfulfilled ? onfulfilled(result) : (result as R1);
  }
}

// Instrumentation: counts DB round-trips and outbound HTTP attempts.
export let queryCount = 0;
export function resetQueryCount() {
  queryCount = 0;
}

/**
 * Swaps the transport on the real `supabase` singleton. Returns nothing;
 * src/lib/safety-engine.ts keeps its own import of that same object.
 */
export async function installShim() {
  const pg = await bootstrapDb();
  const { supabase } = await import("../../src/lib/supabase.js");

  (supabase as any).from = (table: string) => new QueryBuilder(pg, table);
  (supabase as any).rpc = async (fn: string, args: Record<string, unknown>) => {
    try {
      const keys = Object.keys(args);
      const params = keys.map((_, i) => `$${i + 1}`).join(", ");
      const res = await pg.query(`SELECT * FROM ${fn}(${params})`, keys.map((k) => args[k]));
      queryCount++;
      return { data: res.rows, error: null };
    } catch (e: any) {
      return { data: null, error: { message: e?.message ?? String(e) } };
    }
  };
  return pg;
}
