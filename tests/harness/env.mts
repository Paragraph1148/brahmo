// Dummy Supabase env so src/lib/supabase.ts constructs without throwing.
// No network call is ever made: tests/harness/db.ts replaces the transport
// and tests/harness/no-network.ts hard-fails the process if anything dials out.
process.env.NEXT_PUBLIC_SUPABASE_URL ??= "http://harness.invalid";
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??= "harness-anon-key";
