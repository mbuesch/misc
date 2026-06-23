# Check if cargo is available
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "Error: cargo not found."
    Read-Host -Prompt "Press Enter to exit"
    exit 1
}

# Get the list of installed packages (lines starting with non-whitespace, first token)
$packages = cargo install --list |
    Where-Object { $_ -match '^[^\s]' } |
    ForEach-Object { ($_ -split '\s+',2)[0] }

# Packages to skip
$skippedPackages = @(
    "avr-postprocess"
)

# Packages to install with --locked
$lockedPackages = @(
    "bacon",
    "cargo-vet",
    "dioxus-cli"
)

foreach ($pkg in $packages) {
    Write-Host "`nUpdating $pkg"

    if ($skippedPackages -contains $pkg) {
        Write-Host "Skipped."
        continue
    }

    $installArgs = @()
    if ($lockedPackages -contains $pkg) {
        $installArgs += "--locked"
    }

    # Preserve additional args passed to the script
    if ($args) {
        $installArgs += $args
    }

    $installArgs += $pkg

    $cmdArgs = @("install") + $installArgs

    & cargo @cmdArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to update $pkg"
        Read-Host -Prompt "Press Enter to exit"
        exit 1
    }
}

Read-Host -Prompt "Press Enter to exit"
exit 0
