<#
.SYNOPSIS
  Speak a line with Windows' built-in speech synthesis (SAPI, no download) and record its mouth shapes.

.DESCRIPTION
  Writes <OutputDirectory>\line.wav and <OutputDirectory>\visemes.json: SAPI's VisemeReached events (22 mouth
  shapes with start times and durations). Their times run on a different clock from the WAV; align_visemes.py
  rescales them onto the WAV's measured speech before speak_demo.py uses them. The first installed male voice is
  used ("Microsoft David Desktop" on the Raider workstation).

.EXAMPLE
  powershell -NoProfile -File scripts\revamp\raider\speak_line.ps1 -OutputDirectory work\raider-revamp\speech
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $OutputDirectory,
    [string] $Line = "Name's Raider. Stay close, keep your head down, and we'll get out of here alive.",
    [int] $Rate = -1
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$out = (Resolve-Path $OutputDirectory).Path
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$male = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Gender -eq 'Male' } | Select-Object -First 1
if ($male) { $synth.SelectVoice($male.VoiceInfo.Name) }
$synth.Rate = $Rate
$global:visemes = New-Object System.Collections.ArrayList
$handler = [System.EventHandler[System.Speech.Synthesis.VisemeReachedEventArgs]]{
    param($sender, $e)
    [void]$global:visemes.Add(@{ t = $e.AudioPosition.TotalSeconds; d = $e.Duration.TotalSeconds; v = $e.Viseme })
}
$synth.add_VisemeReached($handler)
$synth.SetOutputToWaveFile((Join-Path $out 'line.wav'))
$synth.Speak($Line)
$synth.SetOutputToNull()
$synth.Dispose()
$voice = if ($male) { $male.VoiceInfo.Name } else { 'default' }
$json = @{ line = $Line; voice = $voice; visemes = $global:visemes } | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $out 'visemes.json'), $json, (New-Object System.Text.UTF8Encoding $false))
Write-Host ("SPEAK_LINE_OK {0} visemes, voice {1}" -f $global:visemes.Count, $voice)
