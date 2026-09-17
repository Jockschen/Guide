import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const startupFiles = [
  "start.bat",
  "open.bat",
  "scripts/start.ps1",
  "scripts/open.ps1",
  "scripts/stop.ps1",
  "scripts/start-opentalking.ps1",
  "scripts/setup-opentalking.ps1",
  "scripts/setup-opentalking-runtime.ps1",
  "scripts/check-opentalking-assets.ps1"
];

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

for (const relativePath of startupFiles) {
  const content = readFileSync(path.join(root, relativePath), "utf-8");
  assert(/^[\x00-\x7F]*$/.test(content), `${relativePath} contains non-ASCII text that can break Windows PowerShell/cmd code pages.`);
}

const startScript = readFileSync(path.join(root, "scripts/start.ps1"), "utf-8");
const startBat = readFileSync(path.join(root, "start.bat"), "utf-8");
const openScript = readFileSync(path.join(root, "scripts/open.ps1"), "utf-8");
const openBat = readFileSync(path.join(root, "open.bat"), "utf-8");
assert(startBat.includes("if errorlevel 1"), "start.bat must keep the window open when startup fails.");
assert(startBat.includes("pause"), "start.bat must pause after startup failures so users can read errors.");
assert(startScript.includes("[switch]$NoBrowser"), "scripts/start.ps1 must support -NoBrowser for automated checks.");
assert(startScript.includes('Start-Process "http://127.0.0.1:$frontendPort"'), "scripts/start.ps1 must open the tourist app after startup.");
assert(startScript.includes("function Start-HiddenService"), "scripts/start.ps1 must launch long-running services through tracked hidden launchers.");
assert(startScript.includes("$psi.UseShellExecute = $true"), "scripts/start.ps1 must launch detached hidden service processes through ProcessStartInfo.");
assert(startScript.includes("[System.Diagnostics.ProcessWindowStyle]::Hidden"), "scripts/start.ps1 must hide service windows when launching detached processes.");
assert(startScript.includes('Start-HiddenService -Name "opentalking" -FilePath $opentalkingPython -Arguments $opentalkingArgs'), "scripts/start.ps1 must start OpenTalking with its configured Python runtime.");
assert(startScript.includes('Start-HiddenService -Name "backend" -FilePath $venvPython -Arguments $backendArgs'), "scripts/start.ps1 must start the backend with Python.");
assert(startScript.includes('Start-HiddenService -Name "frontend" -FilePath $nextCommand -Arguments $frontendArgs'), "scripts/start.ps1 must start the frontend with next.cmd.");
assert(startScript.includes('$Name-$stamp.command.txt'), "scripts/start.ps1 must write per-run service command records for debugging.");
assert(startScript.includes('$Name-$stamp.out.log'), "scripts/start.ps1 must write per-run stdout logs for services.");
assert(startScript.includes('$Name-$stamp.err.log'), "scripts/start.ps1 must write per-run stderr logs for services.");
assert(startScript.includes('$Name-$stamp.exit.log'), "scripts/start.ps1 must write per-run exit logs for services.");
assert(startScript.includes("runtime-scripts"), "scripts/start.ps1 must write persistent launcher scripts for hidden services.");
assert(startScript.includes("& $exe @arguments"), "scripts/start.ps1 launchers must invoke service executables with structured arguments.");
assert(!startScript.includes('Start-HiddenProcess -FilePath "cmd.exe"'), "scripts/start.ps1 must not route hidden service startup through cmd.exe in Unicode workspaces.");
assert(!startScript.includes("Start-Process @startInfo"), "scripts/start.ps1 must not use Start-Process for hidden services because Path/PATH collisions break this Windows setup.");
assert(openBat.includes("scripts\\open.ps1"), "open.bat must call scripts/open.ps1.");
assert(startScript.includes("opentalking_port = $opentalkingPort"), "scripts/start.ps1 must persist the OpenTalking bridge port for cleanup.");
assert(readFileSync(path.join(root, "scripts/stop.ps1"), "utf-8").includes("uvicorn server.opentalking_bridge:app"), "scripts/stop.ps1 must stop the OpenTalking bridge process too.");
assert(openScript.includes("runtime-ports.json"), "scripts/open.ps1 must read runtime-ports.json.");
assert(openScript.includes("function Test-HttpOk"), "scripts/open.ps1 must verify the frontend is responding before opening pages.");
assert(openScript.includes("The Lingjing Guide frontend is not responding"), "scripts/open.ps1 must explain stale port files clearly.");
assert(openScript.includes("Start-Process $touristUrl"), "scripts/open.ps1 must open the tourist app.");
assert(openScript.includes("Start-Process $adminUrl"), "scripts/open.ps1 must open the management center.");

const parseCommand = [
  "$tokens=$null",
  "$errors=$null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\start.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\open.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\start-opentalking.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\setup-opentalking.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\setup-opentalking-runtime.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\\scripts\\check-opentalking-assets.ps1'), [ref]$tokens, [ref]$errors) | Out-Null",
  "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }",
  "Write-Output 'startup scripts audit passed'"
].join("; ");

const powershell = process.platform === "win32" ? "powershell.exe" : "powershell";
const result = spawnSync(powershell, ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", parseCommand], {
  cwd: root,
  encoding: "utf-8"
});

if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
assert(result.status === 0, `PowerShell parser rejected scripts/start.ps1 with exit code ${result.status}.`);
