[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedIcon,

    [Parameter(Mandatory = $true)]
    [ValidateCount(1, 16)]
    [string[]]$ExecutablePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$requiredSizes = @(16, 24, 32, 48, 64, 96, 128, 256)

function Resolve-RequiredFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description not found: $Path"
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-IcoSizes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 6) {
        throw "ICO header is truncated: $Path"
    }

    $reserved = [System.BitConverter]::ToUInt16($bytes, 0)
    $imageType = [System.BitConverter]::ToUInt16($bytes, 2)
    $imageCount = [System.BitConverter]::ToUInt16($bytes, 4)
    if ($reserved -ne 0 -or $imageType -ne 1 -or $imageCount -lt 1) {
        throw "Invalid ICO header: $Path"
    }

    $directoryLength = 6 + (16 * $imageCount)
    if ($bytes.Length -lt $directoryLength) {
        throw "ICO directory is truncated: $Path"
    }

    $sizes = @()
    for ($index = 0; $index -lt $imageCount; $index++) {
        $offset = 6 + (16 * $index)
        $width = [int]$bytes[$offset]
        $height = [int]$bytes[$offset + 1]
        if ($width -eq 0) {
            $width = 256
        }
        if ($height -eq 0) {
            $height = 256
        }
        if ($width -ne $height) {
            throw "ICO entry $index is not square (${width}x${height}): $Path"
        }
        $sizes += $width
    }

    return @($sizes | Sort-Object -Unique)
}

function Get-IconBitmap {
    param(
        [Parameter(Mandatory = $true)]
        [System.Drawing.Icon]$Icon,

        [Parameter(Mandatory = $true)]
        [int]$Size
    )

    $normalizedIcon = [System.Drawing.Icon]::new($Icon, $Size, $Size)
    try {
        return $normalizedIcon.ToBitmap()
    }
    finally {
        $normalizedIcon.Dispose()
    }
}

function Assert-TransparentCorners {
    param(
        [Parameter(Mandatory = $true)]
        [System.Drawing.Bitmap]$Bitmap,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $lastX = $Bitmap.Width - 1
    $lastY = $Bitmap.Height - 1
    $corners = @(
        @(0, 0),
        @($lastX, 0),
        @(0, $lastY),
        @($lastX, $lastY)
    )
    foreach ($corner in $corners) {
        $pixel = $Bitmap.GetPixel($corner[0], $corner[1])
        if ($pixel.A -ne 0) {
            throw "$Description has a non-transparent corner at ($($corner[0]), $($corner[1])) with alpha $($pixel.A)."
        }
    }
}

function Assert-BitmapEqual {
    param(
        [Parameter(Mandatory = $true)]
        [System.Drawing.Bitmap]$Expected,

        [Parameter(Mandatory = $true)]
        [System.Drawing.Bitmap]$Actual,

        [Parameter(Mandatory = $true)]
        [string]$ActualPath
    )

    if ($Expected.Width -ne $Actual.Width -or $Expected.Height -ne $Actual.Height) {
        throw "Embedded icon size mismatch for ${ActualPath}: expected $($Expected.Width)x$($Expected.Height), found $($Actual.Width)x$($Actual.Height)."
    }

    for ($y = 0; $y -lt $Expected.Height; $y++) {
        for ($x = 0; $x -lt $Expected.Width; $x++) {
            $expectedArgb = $Expected.GetPixel($x, $y).ToArgb()
            $actualArgb = $Actual.GetPixel($x, $y).ToArgb()
            if ($expectedArgb -ne $actualArgb) {
                throw "Embedded icon pixel mismatch for ${ActualPath} at ($x, $y): expected ARGB $expectedArgb, found $actualArgb."
            }
        }
    }
}

$resolvedIcon = Resolve-RequiredFile -Path $ExpectedIcon -Description "Expected ICO"
$actualSizes = @(Get-IcoSizes -Path $resolvedIcon)
$missingSizes = @($requiredSizes | Where-Object { $_ -notin $actualSizes })
if ($missingSizes.Count -gt 0) {
    throw "ICO is missing required sizes $($missingSizes -join ', '): $resolvedIcon"
}

$previewIcon = [System.Drawing.Icon]::new($resolvedIcon, 256, 256)
$largeBitmap = $null
$expectedIcon32 = $null
$expectedBitmap32 = $null
try {
    $largeBitmap = $previewIcon.ToBitmap()
    if ($largeBitmap.Width -ne $largeBitmap.Height -or $largeBitmap.Width -lt 128) {
        throw "Expected ICO did not decode a square preview frame of at least 128px: $resolvedIcon"
    }
    Assert-TransparentCorners -Bitmap $largeBitmap -Description "Expected ICO preview frame"
    $center = [int][Math]::Floor($largeBitmap.Width / 2)
    $centerPixel = $largeBitmap.GetPixel($center, $center)
    if ($centerPixel.A -eq 0) {
        throw "Expected ICO preview frame has no visible center content: $resolvedIcon"
    }

    $expectedIcon32 = [System.Drawing.Icon]::new($resolvedIcon, 32, 32)
    $expectedBitmap32 = $expectedIcon32.ToBitmap()

    foreach ($path in $ExecutablePath) {
        $resolvedExecutable = Resolve-RequiredFile -Path $path -Description "Executable"
        $embeddedIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($resolvedExecutable)
        if ($null -eq $embeddedIcon) {
            throw "Executable has no associated icon: $resolvedExecutable"
        }

        $actualBitmap32 = $null
        try {
            $actualBitmap32 = Get-IconBitmap -Icon $embeddedIcon -Size 32
            Assert-BitmapEqual -Expected $expectedBitmap32 -Actual $actualBitmap32 -ActualPath $resolvedExecutable
        }
        finally {
            if ($null -ne $actualBitmap32) {
                $actualBitmap32.Dispose()
            }
            $embeddedIcon.Dispose()
        }

        Write-Host "Verified embedded 32px icon: $resolvedExecutable"
    }
}
finally {
    if ($null -ne $expectedBitmap32) {
        $expectedBitmap32.Dispose()
    }
    if ($null -ne $expectedIcon32) {
        $expectedIcon32.Dispose()
    }
    if ($null -ne $largeBitmap) {
        $largeBitmap.Dispose()
    }
    $previewIcon.Dispose()
}

Write-Host "Verified ICO sizes and transparency: $($actualSizes -join ', ')"
