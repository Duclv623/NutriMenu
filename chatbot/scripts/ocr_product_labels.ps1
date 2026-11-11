param([string]$ImageDirectory = 'C:\DATN\data\collected\rag_supplements_2026-10-08\qa\ocr', [string]$OutputDirectory = 'C:\DATN\data\collected\rag_supplements_2026-10-08\extracted')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$adapter = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await-Result($Operation, $ResultType) {
    $task = $adapter.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}
$fileType = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$streamType = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$decoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$bitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$resultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$engine = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]::TryCreateFromLanguage([Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]::new('en-US'))
$groups = Get-ChildItem -LiteralPath $ImageDirectory -Filter '*.png' | Group-Object { $_.BaseName -replace '-\d+$', '' }
foreach ($group in $groups) {
    $pages = @()
    foreach ($picture in ($group.Group | Sort-Object Name)) {
        $file = Await-Result ($fileType::GetFileFromPathAsync($picture.FullName)) $fileType
        $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode, Windows.Storage, ContentType=WindowsRuntime]::Read)) $streamType
        $decoder = Await-Result ($decoderType::CreateAsync($stream)) $decoderType
        $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) $bitmapType
        $result = Await-Result ($engine.RecognizeAsync($bitmap)) $resultType
        $lines = @($result.Lines | ForEach-Object {
            @{text=$_.Text; words=@($_.Words | ForEach-Object { @{text=$_.Text; x=$_.BoundingRect.X; y=$_.BoundingRect.Y; width=$_.BoundingRect.Width; height=$_.BoundingRect.Height} })}
        })
        $pages += @{page=[int]($picture.BaseName -replace '^.*-', ''); text=$result.Text; lines=$lines; image_path=('qa/ocr/' + $picture.Name); image_sha256=(Get-FileHash -LiteralPath $picture.FullName -Algorithm SHA256).Hash.ToLower()}
        $bitmap.Dispose()
        $stream.Dispose()
    }
    $record = @{source_id=$group.Name; engine='Windows.Media.Ocr'; recognizer_language='en-US'; warning='OCR is a draft; nutrition values require visual cell review. Original PDFs are preserved.'; pages=$pages}
    $record | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory ($group.Name + '.ocr.pages.json')) -Encoding UTF8
    Write-Output ($group.Name + ': ' + $pages.Count + ' pages OCR completed')
}
