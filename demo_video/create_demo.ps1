$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $PSScriptRoot 'assets'
$output = Join-Path $PSScriptRoot 'output'
$slides = Join-Path $output 'slides'
$hero = Join-Path $assets 'roadsense-hero.png'
$detect = Join-Path $root 'runs\detect\results\road_damage_smoke\rdd2022_showcase.jpg'
$narrationText = Get-Content -Raw (Join-Path $PSScriptRoot 'narration.txt')
$narrationWav = Join-Path $output 'roadsense-demo-narration.wav'
$videoOut = Join-Path $output 'roadsense-feature-demo.mp4'
$font = 'C\:/Windows/Fonts/arial.ttf'
$fontBold = 'C\:/Windows/Fonts/arialbd.ttf'

New-Item -ItemType Directory -Force -Path $output, $slides | Out-Null

function Escape-DrawText([string]$text) {
  # Keep FFmpeg's literal \n escape intact so feature descriptions render across lines.
  return $text.Replace(':', '\:').Replace("'", "\'")
}

function New-FeatureSlide([int]$number, [string]$title, [string]$body, [string]$accent) {
  $out = Join-Path $slides ('slide-{0:d2}.png' -f $number)
  $safeTitle = Escape-DrawText $title
  $bodyDraw = @()
  $lineIndex = 0
  foreach ($line in ($body -split '\\n')) {
    $safeLine = Escape-DrawText $line
    $y = 390 + (60 * $lineIndex)
    $bodyDraw += "drawtext=fontfile='$font':text='$safeLine':fontcolor=0xC7D2E3:fontsize=34:x=175:y=$y"
    $lineIndex++
  }
  $filter = "drawbox=x=0:y=0:w=1920:h=1080:color=0x07111F:t=fill,drawbox=x=120:y=205:w=11:h=575:color=${accent}:t=fill,drawtext=fontfile='$fontBold':text='$safeTitle':fontcolor=white:fontsize=72:x=175:y=255," + ($bodyDraw -join ',') + ",drawtext=fontfile='$fontBold':text='ROADSENSE':fontcolor=${accent}:fontsize=26:x=175:y=875,drawtext=fontfile='$font':text='AI ROAD INTELLIGENCE':fontcolor=0x94A3B8:fontsize=22:x=175:y=920"
  & ffmpeg -loglevel error -y -f lavfi -i 'color=c=0x07111F:s=1920x1080' -frames:v 1 -update 1 -vf $filter $out | Out-Null
}

# Opening visual generated for this demo.
$intro = Join-Path $slides 'slide-01.png'
$introFilter = "scale=1920:1080,setsar=1,drawbox=x=0:y=0:w=1920:h=1080:color=black@0.34:t=fill,drawtext=fontfile='$fontBold':text='ROADSENSE':fontcolor=white:fontsize=96:x=115:y=125,drawtext=fontfile='$font':text='AI-powered road navigation and intelligence':fontcolor=0xD9F7FF:fontsize=38:x=120:y=245"
& ffmpeg -loglevel error -y -i $hero -frames:v 1 -update 1 -vf $introFilter $intro | Out-Null

New-FeatureSlide 2 'Routes that stay on roads' 'Every selected route is resolved against the driving network.\nIf safe road geometry is unavailable, navigation pauses instead of drawing a misleading straight line.' '0x22D3EE'

$visionSlide = Join-Path $slides 'slide-03.png'
$visionFilter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x07111F,setsar=1,drawbox=x=0:y=0:w=1920:h=160:color=0x07111F@0.9:t=fill,drawtext=fontfile='$fontBold':text='Dashcam perception':fontcolor=white:fontsize=64:x=110:y=45,drawtext=fontfile='$font':text='Road-defect model detects potholes and crack categories from consented footage':fontcolor=0xC7D2E3:fontsize=29:x=112:y=118"
& ffmpeg -loglevel error -y -i $detect -frames:v 1 -update 1 -vf $visionFilter $visionSlide | Out-Null

New-FeatureSlide 4 'Confidence-aware sensor fusion' 'GNSS, camera timestamps, and IMU signals are synchronized.\nStale location fixes are rejected. Harsh braking and road vibration add safety context.' '0x38BDF8'
New-FeatureSlide 5 'Traffic intelligence' 'Segment speed, congestion, observed hazards, and external signals become\nclear routing penalties and live re-routing decisions.' '0xA78BFA'
New-FeatureSlide 6 'Safe speed advice' 'Legal speed limits stay separate from advisory speeds.\nApproaching hazards trigger transparent, non-legal safety recommendations.' '0xFBBF24'
New-FeatureSlide 7 'Parking intelligence and privacy' 'Roadside availability is an estimate, not a promise.\nPlate masking, short retention, and provenance controls protect people by design.' '0x10B981'
New-FeatureSlide 8 'Live operations console' 'Operations teams triage hazards, validate confidence, manage closures,\nmonitor fleet health, and prioritize road maintenance.' '0xFB923C'
New-FeatureSlide 9 'Licensed dashcam replay' 'A user-selected local video is sampled frame by frame.\nThe video stays local; only validated, deduplicated RoadEvents are published.' '0xEC4899'
New-FeatureSlide 10 'Safer journeys. Smarter roads.' 'RoadSense transforms consented road observations into\nsafer navigation and evidence-based maintenance.' '0x22D3EE'

if (-not (Test-Path $narrationWav)) {
  Add-Type -AssemblyName System.Speech
  $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $speaker.Rate = 3
  $speaker.Volume = 100
  $speaker.SetOutputToWaveFile($narrationWav)
  $speaker.Speak($narrationText)
  $speaker.Dispose()
}

$durations = @(12, 12, 12, 12, 12, 12, 12, 12, 12, 12)
$args = @('-y')
for ($i = 1; $i -le 10; $i++) {
  $args += @('-loop', '1', '-t', $durations[$i - 1], '-i', (Join-Path $slides ('slide-{0:d2}.png' -f $i)))
}
$args += @('-i', $narrationWav)
$inputs = ((0..9 | ForEach-Object { "[${_}:v]" }) -join '')
$filter = "$inputs`concat=n=10:v=1:a=0,format=yuv420p[v]"
$args += @('-filter_complex', $filter, '-map', '[v]', '-map', '10:a', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-c:a', 'aac', '-b:a', '192k', '-t', '120', '-movflags', '+faststart', $videoOut)
& ffmpeg -loglevel error @args

Write-Host "Created $videoOut"
