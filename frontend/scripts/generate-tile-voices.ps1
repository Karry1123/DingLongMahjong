param([switch]$HonorsOnly)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

$voiceName = 'Microsoft Huihui Desktop'
$outputDir = Join-Path $PSScriptRoot '..\public\audio\tiles'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$labels = @{}
$numbers = @('一', '二', '三', '四', '五', '六', '七', '八', '九')
foreach ($suit in @(@('m', '万'), @('p', '筒'), @('s', '条'))) {
    for ($index = 0; $index -lt 9; $index++) {
        $labels["$($index + 1)$($suit[0])"] = "$($numbers[$index])$($suit[1])"
    }
}
$labels['E'] = '东风'
$labels['S'] = '南风'
$labels['W'] = '西风'
$labels['N'] = '北风'
$labels['C'] = '红中'
$labels['F'] = '发财'
$labels['P'] = '白板'
$labels['CHI'] = '吃'
$labels['PONG'] = '碰'
$labels['GANG'] = '杠'
$labels['WIN'] = '胡了'
$labels['ZIMO'] = '自摸'

$honorFiles = @{ E='dongfeng'; S='nanfeng'; W='xifeng'; N='beifeng'; C='hongzhong'; F='facai'; P='baiban' }
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SelectVoice($voiceName)
    foreach ($code in ($labels.Keys | Sort-Object)) {
        if ($HonorsOnly -and -not $honorFiles.ContainsKey($code)) { continue }
        $file = if ($honorFiles.ContainsKey($code)) { $honorFiles[$code] } else { $code }
        $path = Join-Path $outputDir "$file.wav"
        $synth.SetOutputToWaveFile($path, $format)
        $synth.Speak($labels[$code])
    }
} finally {
    $synth.Dispose()
}
Write-Output "Generated $(if ($HonorsOnly) { 7 } else { $labels.Count }) Mandarin clips in $outputDir"
Write-Output 'Run python scripts/trim-tile-voices.py to remove synthesis padding.'
