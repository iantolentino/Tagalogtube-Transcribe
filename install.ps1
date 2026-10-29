$ErrorActionPreference = 'Stop'

$installDir = Join-Path $env:USERPROFILE 'Tagalogtube-Transcribe'
$workDir = Join-Path $env:TEMP ("tagalogtube-install-" + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $workDir 'source.zip'
$extractDir = Join-Path $workDir 'source'
$repoZip = 'https://github.com/iantolentino/Tagalogtube-Transcribe/archive/refs/heads/main.zip'

try {
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
    Write-Host 'Downloading TagalogTube Transcriber...'
    Invoke-WebRequest -Uri $repoZip -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $extractDir

    $sourceDir = Join-Path $extractDir 'Tagalogtube-Transcribe-main'
    if (-not (Test-Path -LiteralPath $sourceDir)) {
        throw 'The downloaded repository did not contain the expected source folder.'
    }

    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    $files = @('app.py', 'transcriber.py', 'youtube_handler.py', 'requirements.txt',
        'setup_windows.bat', 'run_windows.bat', 'install.ps1', 'README.md', '.gitignore')
    foreach ($file in $files) {
        Copy-Item -LiteralPath (Join-Path $sourceDir $file) -Destination $installDir -Force
    }
    foreach ($folder in @('models', 'transcripts')) {
        New-Item -ItemType Directory -Path (Join-Path $installDir $folder) -Force | Out-Null
    }

    Write-Host "App files installed in $installDir"
    Write-Host 'Setting up Python packages and FFmpeg. This may take several minutes.'
    $setupPath = Join-Path $installDir 'setup_windows.bat'
    $setupCommand = '""{0}" --install"' -f $setupPath
    $setupProcess = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /s /c $setupCommand" -Wait -PassThru -NoNewWindow
    if ($setupProcess.ExitCode -ne 0) {
        throw "Setup failed with exit code $($setupProcess.ExitCode). Check the setup output above. To retry manually, open Command Prompt and run: `"$setupPath`" --install"
    }

    Write-Host 'Launching TagalogTube Transcriber...'
    & (Join-Path $installDir 'run_windows.bat')
}
finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
