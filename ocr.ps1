Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$file = [Windows.Storage.StorageFile]::GetFileFromPathAsync('D:\milu_publish_reverse_20260513\插入文档截图.png').GetAwaiter().GetResult()
$stream = $file.OpenReadAsync().GetAwaiter().GetResult()
$decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream).GetAwaiter().GetResult()
$bitmap = $decoder.GetPixelDataAsync().GetAwaiter().GetResult()
$result = $engine.RecognizeAsync($bitmap).GetAwaiter().GetResult()
$result.Text