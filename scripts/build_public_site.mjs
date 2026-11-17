/** Build a static site using the existing web toolchain and shared guide. */
import { cp, mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "apps/web");
const source = join(root, "apps/site");
const destination = join(root, "dist/public-site");
const staging = await mkdtemp(join(web, ".public-site-"));
try {
  // Copy only website source, never a deployment environment or local cache.
  for (const entry of ["app", "components", "next.config.mjs", "tsconfig.json"]) {
    await cp(join(source, entry), join(staging, entry), {
      recursive: true,
      filter: (path) => !path.split(/[\\/]/).some((part) => part.startsWith(".env") || ["node_modules", ".next", "out"].includes(part)) && !/\.(key|pem)$/.test(path),
    });
  }
  const tsconfig = JSON.parse(await readFile(join(source, "tsconfig.json"), "utf8"));
  tsconfig.compilerOptions.paths["@/*"] = ["../*"];
  await writeFile(join(staging, "tsconfig.json"), JSON.stringify(tsconfig, null, 2));
  await cp(join(web, "postcss.config.mjs"), join(staging, "postcss.config.mjs"));
  const publicDir = join(staging, "public");
  await mkdir(join(publicDir, "guide"), { recursive: true });
  const manifest = JSON.parse(await readFile(join(web, "public/guide/manifest.json"), "utf8"));
  for (const shot of manifest.screenshots) {
    if (!/^[a-z0-9-]+$/.test(shot.name)) throw new Error("Invalid screenshot filename");
    await cp(join(web, `public/guide/${shot.name}.png`), join(publicDir, `guide/${shot.name}.png`));
  }
  await cp(join(web, "public/guide/manifest.json"), join(publicDir, "guide/manifest.json"));
  await cp(join(web, "public/careerpilot-avatar.svg"), join(publicDir, "careerpilot-avatar.svg"));
  await writeFile(join(publicDir, ".nojekyll"), "");
  // A project-local package boundary prevents Next from selecting another app.
  await writeFile(join(staging, "package.json"), JSON.stringify({ name: "careerpilot-public-site", private: true }));
  const code = await new Promise((done, reject) => {
    const child = spawn(process.execPath, [join(web, "node_modules/next/dist/bin/next"), "build", staging, "--webpack"], {
      cwd: staging, stdio: "inherit", env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
    });
    child.on("error", reject);
    child.on("exit", done);
  });
  if (code !== 0) throw new Error(`Public site build exited with ${code}`);
  // Replace only our generated artifact, after the build has succeeded.
  await mkdir(dirname(destination), { recursive: true });
  await rm(destination, { recursive: true, force: true });
  await rename(join(staging, "out"), destination);
  console.log(`Static site built: ${destination}`);
} finally {
  await rm(staging, { recursive: true, force: true });
}
