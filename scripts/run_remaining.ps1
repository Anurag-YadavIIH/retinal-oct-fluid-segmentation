<#
Run the remaining GPU work of 2026-10-04 as one unattended chain, strictly one job at a time.

Launched by the author from an interactive terminal kept open (docs/07 section 17.8). If the
terminal is the VS Code integrated terminal, VS Code must stay open for the whole chain. Runs
once: it refuses to start if artifacts\chain\status.txt already exists. Never retries a step.

  0. The open val bucket of cirrus_holdout_stage2, evaluated twice, then compared exactly.
     Records STEP0 IDENTICAL, DIFFER or FAILED. Unlocks nothing.
  1. topcon_holdout training: OCUVAL_CACHE_DIR on D:, fresh run directory, --epochs 150,
     no session limit. Runs whatever step 0 found. Succeeds only on exit 0 AND a final
     session_end with fold_complete true (04_train.py returns 0 however the session ended).
  2. cirrus sealed re-run, test then in_domain_ref (docs/08 D7, docs/07 section 17.7b), to new
     files. Each is compared exactly with the 767c8e5 record straight after it runs; on any
     difference the chain stops before anything else is unlocked.
  3. spectralis_holdout one-time evaluation, test then in_domain_ref (docs/07 sections 17, 19).
  4. topcon_holdout one-time evaluation, test then in_domain_ref -- only if step 1 succeeded.

Steps 2-4 run ONLY if step 0 recorded IDENTICAL; otherwise no sealed bucket is unlocked. Any
evaluation exiting non-zero stops the chain. A failed step 1 skips step 4 only.
#>

$ErrorActionPreference = 'Continue'   # native stderr must not terminate the chain
Set-Location (Split-Path -Parent $PSScriptRoot)

$Py = '.venv\Scripts\python.exe'
$Chain = 'artifacts\chain'
$Status = Join-Path $Chain 'status.txt'
$Approver = 'Anurag Yadav'

$CirrusRun = 'artifacts\runs\cirrus_holdout_stage2'
$SpectralisRun = 'artifacts\runs\spectralis_holdout_stage3'
$TopconRun = 'artifacts\runs\topcon_holdout_stage3'
$Repro = Join-Path $CirrusRun 'repro'
$TopconCache = 'D:\ocuval_cache'

function Log([string]$Message) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $Status -Value $line -Encoding ASCII
    Write-Host $line
}

# One python invocation, stdout and stderr to their own logs. Returns the exit code only:
# both streams go to files, so nothing else reaches the function's output.
function Invoke-Step([string]$Name, [string[]]$Arguments) {
    $out = Join-Path $Chain "$Name.out.log"
    $err = Join-Path $Chain "$Name.err.log"
    Log "START $Name"
    & $Py -u @Arguments 1> $out 2> $err
    $code = $LASTEXITCODE
    Log "END   $Name exit $code"
    return $code
}

function Invoke-Evaluation([string]$Name, [string]$Run, [string]$Bucket, [string]$Reason, [string]$Output) {
    $arguments = @('scripts\05_evaluate.py', '--run', $Run, '--bucket', $Bucket,
        '--unlock-bucket', '--unlock-reason', $Reason, '--approved-by', $Approver)
    if ($Output) { $arguments += @('--output', $Output) }
    return Invoke-Step $Name $arguments
}

function Stop-Chain([string]$Why) {
    Log "CHAIN STOPPED: $Why"
    Log 'CHAIN END'
    exit 1
}

# ---- pre-flight: refuse rather than overwrite or run twice --------------------------------
if (Test-Path $Status) {
    Write-Host "!! $Status exists: this chain has already run. It never runs twice."
    exit 2
}
$refusals = @()
if (git status --porcelain) { $refusals += 'working tree is not clean' }
if (Get-Process python -ErrorAction SilentlyContinue) { $refusals += 'a python process is already running' }
if (Test-Path $TopconRun) { $refusals += "$TopconRun exists; the topcon run must be fresh" }
if (Test-Path $Repro) { $refusals += "$Repro exists; re-run records must not overwrite anything" }
foreach ($bucket in 'test', 'in_domain_ref') {
    if (Test-Path (Join-Path $SpectralisRun "evaluation_$bucket.json")) {
        $refusals += "spectralis evaluation_$bucket.json already exists"
    }
}
if (-not (Test-Path 'D:\')) { $refusals += 'drive D: is not available for the topcon cache' }
if ($refusals) {
    foreach ($r in $refusals) { Write-Host "!! refused: $r" }
    exit 2
}
New-Item -ItemType Directory -Force -Path $Chain, $Repro, $TopconCache | Out-Null
Log "CHAIN START at $(git rev-parse HEAD)"

# ---- step 0: is evaluation reproducible run to run? ---------------------------------------
$valA = Join-Path $Repro 'evaluation_val_a.json'
$valB = Join-Path $Repro 'evaluation_val_b.json'
$step0 = 'FAILED'
$a = Invoke-Step 'step0_val_a' @('scripts\05_evaluate.py', '--run', $CirrusRun, '--bucket', 'val', '--output', $valA)
if ($a -eq 0) {
    $b = Invoke-Step 'step0_val_b' @('scripts\05_evaluate.py', '--run', $CirrusRun, '--bucket', 'val', '--output', $valB)
    if ($b -eq 0) {
        $c = Invoke-Step 'step0_compare' @('scripts\compare_evaluation_records.py', $valA, $valB)
        if ($c -eq 0) { $step0 = 'IDENTICAL' } elseif ($c -eq 1) { $step0 = 'DIFFER' }
    }
}
Log "STEP0 $step0"

# ---- step 1: topcon_holdout training, whatever step 0 found -------------------------------
$env:OCUVAL_CACHE_DIR = $TopconCache
$t = Invoke-Step 'step1_train_topcon' @('scripts\04_train.py', '--fold', 'configs\folds\topcon_holdout.yaml',
    '--run-dir', $TopconRun, '--epochs', '150')
Remove-Item Env:OCUVAL_CACHE_DIR
$ends = @()
$epochs = Join-Path $TopconRun 'epochs.jsonl'
if (Test-Path $epochs) {
    $ends = @(Get-Content $epochs | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { $_.event -eq 'session_end' })
}
$last = if ($ends.Count) { $ends[-1] } else { $null }
$trained = ($t -eq 0) -and ($null -ne $last) -and ($last.fold_complete -eq $true)
if ($trained) {
    Log "STEP1 TRAINED stopped_by=$($last.stopped_by) next_epoch=$($last.next_epoch)"
} else {
    $by = if ($last) { $last.stopped_by } else { 'no session_end' }
    Log "STEP1 NOT COMPLETE exit=$t stopped_by=$by -- topcon will not be evaluated"
}

# ---- steps 2-4: sealed buckets, only after IDENTICAL --------------------------------------
if ($step0 -ne 'IDENTICAL') {
    Log "STEPS 2-4 SKIPPED: step 0 recorded $step0, so no sealed bucket is unlocked today"
    Log 'CHAIN END'
    exit 0
}

# step 2: cirrus re-run, each bucket compared with its 767c8e5 record before the next unlock
$cirrusReason = 'deterministic re-run under docs/07 section 17.7b to repair docs/08 D7 ' +
    '(per-volume rows not persisted); no change to model, checkpoint, threshold or metric ' +
    'definitions; every aggregate compared exactly with the 767c8e5 record'
foreach ($bucket in 'test', 'in_domain_ref') {
    $rerun = Join-Path $Repro "evaluation_${bucket}_rerun.json"
    $e = Invoke-Evaluation "step2_cirrus_$bucket" $CirrusRun $bucket $cirrusReason $rerun
    if ($e -ne 0) { Stop-Chain "cirrus $bucket evaluation exited $e" }
    $c = Invoke-Step "step2_compare_$bucket" @('scripts\compare_evaluation_records.py',
        (Join-Path $CirrusRun "evaluation_$bucket.json"), $rerun)
    if ($c -ne 0) { Stop-Chain "cirrus $bucket re-run does not reproduce 767c8e5 (compare exit $c)" }
    Log "STEP2 cirrus $bucket REPRODUCES 767c8e5"
}

# step 3: spectralis one-time evaluation
$oneTime = 'pre-registered one-time Stage 3 evaluation per docs/07 section 17, with the ' +
    'secondary analyses pre-registered in docs/07 section 19'
foreach ($bucket in 'test', 'in_domain_ref') {
    $e = Invoke-Evaluation "step3_spectralis_$bucket" $SpectralisRun $bucket $oneTime $null
    if ($e -ne 0) { Stop-Chain "spectralis $bucket evaluation exited $e" }
}
Log 'STEP3 spectralis evaluated'

# step 4: topcon one-time evaluation, only if it trained to completion
if (-not $trained) {
    Log 'STEP4 SKIPPED: topcon training did not complete'
} else {
    foreach ($bucket in 'test', 'in_domain_ref') {
        $e = Invoke-Evaluation "step4_topcon_$bucket" $TopconRun $bucket $oneTime $null
        if ($e -ne 0) { Stop-Chain "topcon $bucket evaluation exited $e" }
    }
    Log 'STEP4 topcon evaluated'
}
Log 'CHAIN END'
exit 0
