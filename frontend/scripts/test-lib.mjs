// Runs the plain-Node tests in lib/*.test.ts (the same `assert`-only style as before,
// no test framework). Node's ESM loader wants an explicit extension on relative imports,
// which the bundler does not, so each test file is copied next to itself with ".ts"
// added to the imports of sibling modules, run with Node's TypeScript stripping, and the
// copy removed. Exit code is non-zero if any file fails.
//
//   npm test                 all of them
//   npm test -- quiz chat    only lib/quiz.test.ts and lib/chat.test.ts

import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const lib = join(dirname(fileURLToPath(import.meta.url)), "..", "lib");
const only = process.argv.slice(2);

const tests = readdirSync(lib)
  .filter((f) => f.endsWith(".test.ts"))
  .filter((f) => only.length === 0 || only.some((name) => f === `${name}.test.ts`))
  .sort();

if (tests.length === 0) {
  console.error("No matching test files in lib/.");
  process.exit(1);
}

let failed = 0;
let totalPassed = 0;

for (const file of tests) {
  const source = readFileSync(join(lib, file), "utf8");
  // "./graph-model" -> "./graph-model.ts" when lib/graph-model.ts exists.
  const rewritten = source.replace(/(from\s+["'])\.\/([\w-]+)(["'])/g, (match, pre, name, post) =>
    existsSync(join(lib, `${name}.ts`)) ? `${pre}./${name}.ts${post}` : match
  );
  const temp = join(lib, `_run-${file}`);
  writeFileSync(temp, rewritten);
  let result;
  try {
    result = spawnSync(process.execPath, ["--experimental-strip-types", "--no-warnings", temp], {
      encoding: "utf8",
    });
  } finally {
    rmSync(temp, { force: true });
  }

  const passed = Number(/(\d+) passed/.exec(result.stdout)?.[1] ?? 0);
  if (result.status === 0) {
    totalPassed += passed;
    console.log(`ok    ${file.replace(".test.ts", "").padEnd(14)} ${passed} passed`);
  } else {
    failed++;
    console.log(`FAIL  ${file}`);
    console.log(result.stdout);
    console.log(result.stderr);
  }
}

console.log(`\n${totalPassed} passed${failed ? `, ${failed} file(s) FAILED` : ""}`);
process.exit(failed ? 1 : 0);
