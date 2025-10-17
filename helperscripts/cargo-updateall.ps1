# Check if cargo is available
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "Error: cargo not found."
    Read-Host -Prompt "Press Enter to exit"
    exit 1
}

# Get the list of installed packages
$packages = cargo install --list | ForEach-Object {
    # Split the line and take the first element (package name)
    $parts = $_.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
    if ($parts.Length -gt 0 -and $_ -match '^[^\s]') {
        $parts[0]
    }
}

# Packages to skip
$skippedPackages = @(
    "atdf2svd",
    "svd2rust",
    "svdtools",
    "avr-postprocess",
    "dioxus-cli"
)

# Packages to install with --locked
$lockedPackages = @(
    "bacon",
    "cargo-vet"
)

foreach ($pkg in $packages) {
    Write-Host "`nUpdating $pkg"

    if ($skippedPackages -contains $pkg) {
        Write-Host "Skipped."
        continue
    }

    $installArgs = New-Object System.Collections.ArrayList
    if ($lockedPackages -contains $pkg) {
        $installArgs.Add("--locked") | Out-Null
    }

    # Add any additional arguments passed to the script
    if ($args) {
        $installArgs.AddRange($args)
    }

    $installArgs.Add($pkg) | Out-Null

    # Run cargo install
    cargo install @installArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to update $pkg"
        Read-Host -Prompt "Press Enter to exit"
        exit 1
    }
}

Read-Host -Prompt "Press Enter to exit"
exit 0
