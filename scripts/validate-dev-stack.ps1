# Usage (from repo root): powershell -ExecutionPolicy Bypass -File scripts/validate-dev-stack.ps1
# Expects: backend on 127.0.0.1:7860, Vite on 127.0.0.1:5174 (see frontend/vite.config.ts)
$ErrorActionPreference = "Stop"
$base = @(
    @{ n = "backend GET /api"; u = "http://127.0.0.1:7860/api" },
    @{ n = "backend GET /api/config/model"; u = "http://127.0.0.1:7860/api/config/model" },
    @{ n = "vite GET /"; u = "http://127.0.0.1:5174/" },
    @{ n = "vite proxy GET /api"; u = "http://127.0.0.1:5174/api" },
    @{ n = "vite GET / (localhost)"; u = "http://localhost:5174/" }
)
$ok = 0
foreach ($t in $base) {
    try {
        $r = Invoke-WebRequest -Uri $t.u -UseBasicParsing -TimeoutSec 15
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) {
            Write-Host "OK  $($t.n) [$($r.StatusCode)]"
            $ok++
        } else {
            Write-Host "BAD $($t.n) status=$($r.StatusCode)"
        }
    } catch {
        Write-Host "FAIL $($t.n) :: $($_.Exception.Message)"
    }
}
Write-Host "---"
if ($ok -eq $base.Count) { Write-Host "All $($base.Count) checks passed."; exit 0 }
Write-Host "Only $ok / $($base.Count) passed."
exit 1
