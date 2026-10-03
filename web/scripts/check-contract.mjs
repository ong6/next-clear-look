import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const temporaryDirectory = await mkdtemp(path.join(tmpdir(), "ncl-contract-"));
const generatedPath = path.join(temporaryDirectory, "schema.ts");
const expectedPath = new URL("../src/api/generated/schema.ts", import.meta.url);

try {
  const result = spawnSync(
    "pnpm",
    ["exec", "openapi-typescript", "../contracts/openapi.yaml", "-o", generatedPath],
    {
      cwd: new URL("..", import.meta.url),
      encoding: "utf8",
    },
  );
  if (result.status !== 0) {
    process.stderr.write(result.stderr);
    process.exit(result.status ?? 1);
  }
  const [expected, generated] = await Promise.all([
    readFile(expectedPath, "utf8"),
    readFile(generatedPath, "utf8"),
  ]);
  if (expected !== generated) {
    process.stderr.write("Generated OpenAPI types are stale. Run: pnpm --dir web generate:api\n");
    process.exitCode = 1;
  } else {
    process.stdout.write("OpenAPI types match contracts/openapi.yaml.\n");
  }
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
