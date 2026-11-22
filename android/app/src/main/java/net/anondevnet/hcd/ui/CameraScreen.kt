package net.anondevnet.hcd.ui

import android.util.Size
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import net.anondevnet.hcd.vision.GlintDetector
import net.anondevnet.hcd.vision.GlintHit
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference

@Composable
fun CameraScreen(enabled: Boolean) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var mode by remember { mutableStateOf(GlintDetector.Mode.GLINT) }
    var torchOn by remember { mutableStateOf(false) }
    var hits by remember { mutableStateOf<List<GlintHit>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    val detector = remember { GlintDetector() }
    val modeRef = remember { AtomicReference(mode) }
    modeRef.set(mode)
    val cameraRef = remember { AtomicReference<Camera?>(null) }
    val previewView = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }

    DisposableEffect(lifecycleOwner, enabled) {
        if (!enabled) {
            return@DisposableEffect onDispose { }
        }
        val executor = Executors.newSingleThreadExecutor()
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener(
            {
                try {
                    val provider = future.get()
                    val preview = Preview.Builder().build().also {
                        it.surfaceProvider = previewView.surfaceProvider
                    }
                    val analysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                        .setTargetResolution(Size(360, 640))
                        .build()
                    analysis.setAnalyzer(executor) { image ->
                        try {
                            val bitmap = image.toBitmap()
                            val width = 240
                            val height = ((width.toFloat() / bitmap.width) * bitmap.height).toInt().coerceAtLeast(1)
                            val scaled = android.graphics.Bitmap.createScaledBitmap(bitmap, width, height, true)
                            val detected = detector.detect(scaled, modeRef.get())
                            onHitsNormalized(detected, scaled.width, scaled.height, onHits = { hits = it })
                        } catch (ex: Exception) {
                            error = ex.message ?: "analyzer failed"
                        } finally {
                            image.close()
                        }
                    }
                    provider.unbindAll()
                    cameraRef.set(
                        provider.bindToLifecycle(
                            lifecycleOwner,
                            CameraSelector.DEFAULT_BACK_CAMERA,
                            preview,
                            analysis,
                        ),
                    )
                } catch (ex: Exception) {
                    error = ex.message ?: "could not open camera"
                }
            },
            ContextCompat.getMainExecutor(context),
        )
        onDispose {
            try {
                if (future.isDone) future.get().unbindAll()
            } catch (_: Exception) {
            }
            cameraRef.set(null)
            executor.shutdown()
        }
    }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (enabled) {
                AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
                DetectionOverlay(hits)
            } else {
                Text(
                    "Camera permission is required for lens-glint and IR detection.",
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
            }
            Text(
                text = if (mode == GlintDetector.Mode.IR) "IR mode · ${hits.size} stable" else "Glint mode · ${hits.size} stable",
                color = Color.White,
                modifier = Modifier.align(Alignment.TopStart).padding(12.dp),
            )
        }
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            FilterChip(
                selected = mode == GlintDetector.Mode.GLINT,
                onClick = {
                    mode = GlintDetector.Mode.GLINT
                    detector.reset()
                    hits = emptyList()
                },
                label = { Text("Lens glint") },
            )
            FilterChip(
                selected = mode == GlintDetector.Mode.IR,
                onClick = {
                    mode = GlintDetector.Mode.IR
                    detector.reset()
                    hits = emptyList()
                },
                label = { Text("IR dots") },
                modifier = Modifier.padding(start = 8.dp),
            )
            TextButton(
                onClick = {
                    val camera = cameraRef.get()
                    if (camera?.cameraInfo?.hasFlashUnit() == true) {
                        torchOn = !torchOn
                        camera.cameraControl.enableTorch(torchOn)
                    } else {
                        error = "No torch on this camera"
                    }
                },
            ) { Text(if (torchOn) "Torch on" else "Torch") }
        }
        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
        }
        hits.forEach { hit ->
            Text(
                "${hit.kind} score ${"%.2f".format(hit.score)}  seen ${hit.framesSeen}",
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

private fun onHitsNormalized(
    detected: List<GlintHit>,
    width: Int,
    height: Int,
    onHits: (List<GlintHit>) -> Unit,
) {
    onHits(
        detected.map {
            it.copy(
                x = it.x / width,
                y = it.y / height,
                radius = it.radius / width,
            )
        },
    )
}

@Composable
private fun DetectionOverlay(hits: List<GlintHit>) {
    Canvas(Modifier.fillMaxSize()) {
        hits.forEach { hit ->
            val color = if (hit.kind == "ir_dot") Color(0xFFD46EC8) else Color(0xFFE8A04A)
            val center = Offset(hit.x * size.width, hit.y * size.height)
            val radius = maxOf(16f, hit.radius * size.width + 8f)
            drawCircle(color = color, radius = radius, center = center, style = Stroke(width = 5f))
        }
    }
}
