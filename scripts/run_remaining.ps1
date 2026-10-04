<#
Evaluate all three folds under the seeded evaluation path (SRS-091), one job at a time.
Evaluation only: all three folds are trained. Protocol: docs/07 section 17.10.

Launched by the author from an interactive terminal kept open (docs/07 section 17.8). If that
is the VS Code integrated terminal, VS Code must stay open for the whole chain. Runs once: it
refuses to start if artifacts\chain\status.txt already records an EVAL CHAIN START. Never
retries a step. Never overwrites an earlier evaluation output: every output path is new and
the chain refuses to start if any exists.

  0. Two seeded evaluations of the open val bucket of cirrus_holdout_stage2 at this commit,
     compared exactly (SRS-090). Both records must carry the SRS-091 determinism report. If
     the two are not IDENTICAL, the chain stops: NO sealed bucket is unlocked.
  1. cirrus_holdout seeded re-run, test then in_domain_ref (docs/07 sections 17.7b, 17.10).
  2. spectralis_holdout one-time evaluation, test then in_domain_ref (docs/07 sections 17, 19).
  3. topcon_holdout one-time evaluation, test then in_domain_ref (docs/07 sections 17, 19).

Any step exiting non-zero stops the chain. Each step logs to its own files under
artifacts\chain\ and appends its start, end and exit code to artifacts\chain\status.txt, which
is appended to and never truncated (it also holds the earlier chain of 2026-10-04).
#>

$ErrorActionPreference = 'Continue'   # native stderr must not terminate the chain
Set-Location (Split-Path -Parent $PSScriptRoot)

$Py = '.venv\Scripts\python.exe'
$Chain = 'artifacts\chain'
$Status = Join-Path $Chain 'status.txt'
$Approver = 'Anurag Yadav'
$Marker = 'EVAL CHAIN START'

$CirrusRun = 'artifacts\runs\cirrus_holdout_stage2'
$SpectralisRun = 'artifacts\runs\spectralis_holdout_stage3'
$TopconRun = 'artifacts\runs\topcon_holdout_stage3'
$Repro = Join-Path $CirrusRun 'repro'

$ValA = Join-Path $Repro 'evaluation_val_seeded_a.json'
$ValB = Join-Path $Repro 'evaluation_val_seeded_b.json'
$Outputs = [ordered]@{
    'cirrus_test'              = Join-Path $Repro 'evaluation_test_seeded.json'
    'cirrus_in_domain_ref'     = Join-Path $Repro 'evaluation_in_domain_ref_seeded.json'
    'spectralis_test'          = Join-Path $SpectralisRun 'evaluation_test.json'
    'spectralis_in_domain_ref' = Join-Path $SpectralisRun 'evaluation_in_domain_ref.json'
    'topcon_test'              = Join-Path $TopconRun 'evaluation_test.json'
    'topcon_in_domain_ref'     = Join-Path $TopconRun 'evaluation_in_domain_ref.json'
}

$CirrusReason = 'seeded re-run under docs/07 sections 17.10 and 17.7b; defect: evaluation was ' +
    'unseeded (docs/13 2026-10-04, fixed by SRS-091); the 767c8e5 figures are retained as a ' +
    'single unseeded draw; no change to model, checkpoint, threshold or metric definitions'
$OneTimeReason = 'pre-registered one-time Stage 3 evaluation per docs/07 section 17, under the ' +
    'seeded evaluation of section 17.10, with the secondary analyses pre-registered in docs/07 ' +
    'section 19'

function Log([string]$Message) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $Status -Value $line -Encoding ASCII
    Write-Host $line
}

# One python invocation, stdout and stderr to their own logs. Returns the exit code only:
# both streams go to files, so nothing else reaches the function's output.
function Invoke-Step([string]$Name, [string[]]$Arguments) {
    $out = Join-Path $Chain "eval_$Name.out.log"
    $err = Join-Path $Chain "eval_$Name.err.log"
    Log "START $Name"
    & $Py -u @Arguments 1> $out 2> $err
    $code = $LASTEXITCODE
    Log "END   $Name exit $code"
    return $code
}

function Invoke-Sealed([string]$Name, [string]$Run, [string]$Bucket, [string]$Reason, [string]$Output) {
    return Invoke-Step $Name @('scripts\05_evaluate.py', '--run', $Run, '--bucket', $Bucket,
        '--unlock-bucket', '--unlock-reason', $Reason, '--approved-by', $Approver,
        '--output', $Output)
}

function Stop-Chain([string]$Why) {
    Log "CHAIN STOPPED: $Why"
    Log 'CHAIN END'
    exit 1
}

# ---- pre-flight: refuse rather than overwrite, run twice, or run against a dirty tree -----
$refusals = @()
if ((Test-Path $Status) -and (Select-String -Path $Status -SimpleMatch $Marker -Quiet)) {
    $refusals += "$Status already records an $Marker; this chain never runs twice"
}
if (git status --porcelain) { $refusals += 'working tree is not clean' }
if (Get-Process python -ErrorAction SilentlyContinue) { $refusals += 'a python process is already running' }
foreach ($path in @($ValA, $ValB) + @($Outputs.Values)) {
    if (Test-Path $path) { $refusals += "$path exists; no earlier output is ever overwritten" }
}
if (Get-ChildItem -Path $Chain -Filter 'eval_*' -ErrorAction SilentlyContinue) {
    $refusals += "eval_* logs already exist in $Chain"
}
foreach ($run in $CirrusRun, $SpectralisRun, $TopconRun) {
    if (-not (Test-Path (Join-Path $run 'best.pt'))) { $refusals += "$run has no best.pt" }
}
if ($refusals) {
    foreach ($r in $refusals) { Write-Host "!! refused: $r" }
    exit 2
}
New-Item -ItemType Directory -Force -Path $Chain, $Repro | Out-Null
Log "$Marker at $(git rev-parse HEAD)"

# ---- step 0: does the seeded path reproduce itself on this GPU? ---------------------------
$step0 = 'FAILED'
$a = Invoke-Step 'step0_val_seeded_a' @('scripts\05_evaluate.py', '--run', $CirrusRun, '--bucket', 'val', '--output', $ValA)
if ($a -eq 0) {
    $b = Invoke-Step 'step0_val_seeded_b' @('scripts\05_evaluate.py', '--run', $CirrusRun, '--bucket', 'val', '--output', $ValB)
    if ($b -eq 0) {
        # Both records must come from the seeded code: SRS-091 writes notes.determinism and
        # notes.mc_dropout_seeds. Read in Python because the records hold bare NaN tokens,
        # which PowerShell 5.1's ConvertFrom-Json rejects. No double quotes in the program:
        # PowerShell 5.1 mangles them in native arguments, so Python strings use '' here.
        $check = 'import json,sys; ok=all({''determinism'',''mc_dropout_seeds''} <= set(json.load(open(p,encoding=''utf-8''))[''notes'']) for p in sys.argv[1:]); print(''seeded'' if ok else ''NOT seeded''); sys.exit(0 if ok else 1)'
        $s = Invoke-Step 'step0_seeded_check' @('-c', $check, $ValA, $ValB)
        if ($s -ne 0) {
            $step0 = 'NOT_SEEDED'
        } else {
            $c = Invoke-Step 'step0_compare' @('scripts\compare_evaluation_records.py', $ValA, $ValB)
            if ($c -eq 0) { $step0 = 'IDENTICAL' } elseif ($c -eq 1) { $step0 = 'DIFFER' }
        }
    }
}
Log "STEP0 $step0"
if ($step0 -ne 'IDENTICAL') {
    Stop-Chain "step 0 recorded $step0, so no sealed bucket is unlocked"
}

# ---- step 1: cirrus seeded re-run ---------------------------------------------------------
foreach ($bucket in 'test', 'in_domain_ref') {
    $e = Invoke-Sealed "step1_cirrus_$bucket" $CirrusRun $bucket $CirrusReason $Outputs["cirrus_$bucket"]
    if ($e -ne 0) { Stop-Chain "cirrus $bucket evaluation exited $e" }
}
Log 'STEP1 cirrus seeded re-run complete'

# ---- step 2: spectralis one-time evaluation -----------------------------------------------
foreach ($bucket in 'test', 'in_domain_ref') {
    $e = Invoke-Sealed "step2_spectralis_$bucket" $SpectralisRun $bucket $OneTimeReason $Outputs["spectralis_$bucket"]
    if ($e -ne 0) { Stop-Chain "spectralis $bucket evaluation exited $e" }
}
Log 'STEP2 spectralis evaluated'

# ---- step 3: topcon one-time evaluation ---------------------------------------------------
foreach ($bucket in 'test', 'in_domain_ref') {
    $e = Invoke-Sealed "step3_topcon_$bucket" $TopconRun $bucket $OneTimeReason $Outputs["topcon_$bucket"]
    if ($e -ne 0) { Stop-Chain "topcon $bucket evaluation exited $e" }
}
Log 'STEP3 topcon evaluated'
Log 'CHAIN END'
exit 0
