package net.anondevnet.hcd.vision

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.PI
import kotlin.math.sqrt

data class GlintHit(
    val x: Float,
    val y: Float,
    val radius: Float,
    val score: Float,
    val kind: String,
    val framesSeen: Int = 1,
)

class GlintDetector(
    private val persistFrames: Int = 3,
    private val matchDistance: Float = 16f,
) {
    enum class Mode { GLINT, IR }

    private var tracks: List<GlintHit> = emptyList()

    fun reset() {
        tracks = emptyList()
    }

    fun detect(bitmap: Bitmap, mode: Mode): List<GlintHit> {
        val raw = if (mode == Mode.IR) findIr(bitmap) else findGlints(bitmap)
        tracks = stabilize(raw)
        return tracks.filter { it.framesSeen >= persistFrames }
    }

    fun annotate(bitmap: Bitmap, hits: List<GlintHit>): Bitmap {
        val out = bitmap.copy(Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(out)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3f
        }
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 28f
        }
        hits.forEach { hit ->
            paint.color = if (hit.kind == "ir_dot") Color.rgb(212, 110, 200) else Color.rgb(232, 160, 74)
            text.color = paint.color
            canvas.drawCircle(hit.x, hit.y, max(12f, hit.radius + 4f), paint)
            canvas.drawText("${hit.kind} ${"%.2f".format(hit.score)}", hit.x + hit.radius + 8, hit.y, text)
        }
        return out
    }

    private fun findGlints(bitmap: Bitmap): List<GlintHit> {
        val w = bitmap.width
        val h = bitmap.height
        val pixels = IntArray(w * h)
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)
        val gray = IntArray(w * h)
        val hist = IntArray(256)
        for (i in pixels.indices) {
            val c = pixels[i]
            val r = (c shr 16) and 0xff
            val g = (c shr 8) and 0xff
            val b = c and 0xff
            val v = (0.299 * r + 0.587 * g + 0.114 * b).toInt().coerceIn(0, 255)
            gray[i] = v
            hist[v]++
        }
        val thresh = max(220, percentile(hist, w * h, 0.997))
        return blobs(gray, w, h, { gray[it] >= thresh }, minBright = 200, minCirc = 0.62, kind = "glint")
    }

    private fun findIr(bitmap: Bitmap): List<GlintHit> {
        val w = bitmap.width
        val h = bitmap.height
        val pixels = IntArray(w * h)
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)
        val gray = IntArray(w * h)
        val mask = BooleanArray(w * h)
        for (i in pixels.indices) {
            val c = pixels[i]
            val r = (c shr 16) and 0xff
            val g = (c shr 8) and 0xff
            val b = c and 0xff
            gray[i] = (0.299 * r + 0.587 * g + 0.114 * b).toInt()
            val magenta = r > 150 && b > 150 && r + b > 2 * g + 30
            val hot = r > 230 && b > 230 && g > 200
            mask[i] = magenta || hot
        }
        return blobs(gray, w, h, { mask[it] }, minBright = 140, minCirc = 0.5, kind = "ir_dot")
    }

    private fun percentile(hist: IntArray, total: Int, q: Double): Int {
        val target = q * total
        var acc = 0
        for (v in hist.indices) {
            acc += hist[v]
            if (acc >= target) return v
        }
        return 255
    }

    private fun blobs(
        gray: IntArray,
        width: Int,
        height: Int,
        keep: (Int) -> Boolean,
        minBright: Int,
        minCirc: Double,
        kind: String,
    ): List<GlintHit> {
        val seen = BooleanArray(width * height)
        val maxArea = max(6, (0.004 * width * height).toInt())
        val hits = mutableListOf<GlintHit>()
        val stack = IntArray(width * height)
        for (y in 1 until height - 1) {
            for (x in 1 until width - 1) {
                val start = y * width + x
                if (seen[start] || !keep(start)) continue
                var top = 0
                stack[top++] = start
                seen[start] = true
                val pixels = mutableListOf<Int>()
                while (top > 0) {
                    val p = stack[--top]
                    pixels += p
                    val px = p % width
                    val py = p / width
                    for (dy in -1..1) {
                        for (dx in -1..1) {
                            val nx = px + dx
                            val ny = py + dy
                            if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue
                            val ni = ny * width + nx
                            if (seen[ni] || !keep(ni)) continue
                            seen[ni] = true
                            stack[top++] = ni
                        }
                    }
                }
                val area = pixels.size
                if (area < 4 || area > maxArea) continue
                var sx = 0
                var sy = 0
                var minX = width
                var minY = height
                var maxX = 0
                var maxY = 0
                var bright = 0
                for (p in pixels) {
                    val px = p % width
                    val py = p / width
                    sx += px
                    sy += py
                    bright += gray[p]
                    if (px < minX) minX = px
                    if (py < minY) minY = py
                    if (px > maxX) maxX = px
                    if (py > maxY) maxY = py
                }
                val bw = maxX - minX + 1
                val bh = maxY - minY + 1
                val aspect = max(bw, bh).toDouble() / max(1, min(bw, bh))
                if (aspect > 1.6) continue
                var perimeter = 0
                for (p in pixels) {
                    val px = p % width
                    val py = p / width
                    if (!keep(py * width + px - 1) || !keep(py * width + px + 1) ||
                        !keep((py - 1) * width + px) || !keep((py + 1) * width + px)
                    ) {
                        perimeter++
                    }
                }
                val circ = if (perimeter > 0) (4 * PI * area) / (perimeter * perimeter) else 0.0
                if (circ < minCirc * 0.55) continue
                val brightness = bright.toDouble() / area
                if (brightness < minBright) continue
                val cx = sx.toFloat() / area
                val cy = sy.toFloat() / area
                val radius = max(sqrt(area / PI.toDouble()).toFloat(), max(bw, bh) / 2f)
                val score = (0.5 * circ + 0.5 * (brightness / 255.0)).coerceIn(0.0, 1.0).toFloat()
                hits += GlintHit(cx, cy, radius, score, kind)
            }
        }
        return hits.sortedByDescending { it.score }.take(20)
    }

    private fun stabilize(raw: List<GlintHit>): List<GlintHit> {
        val next = mutableListOf<GlintHit>()
        val used = mutableSetOf<Int>()
        for (hit in raw) {
            var best = -1
            var bestD = matchDistance
            for (i in tracks.indices) {
                if (i in used) continue
                val d = hypot((tracks[i].x - hit.x).toDouble(), (tracks[i].y - hit.y).toDouble()).toFloat()
                if (d <= bestD) {
                    bestD = d
                    best = i
                }
            }
            if (best < 0) {
                next += hit
            } else {
                used += best
                next += hit.copy(framesSeen = tracks[best].framesSeen + 1)
            }
        }
        return next
    }
}
