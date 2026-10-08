package dev.halixm.hokacepatcher

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable

/** Locally drawn lavender glass and chessboard geometry inspired by wxq.qq.com. */
class AceHeroDrawable(private val density: Float) : Drawable() {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var opacity = 255

    override fun draw(canvas: Canvas) {
        val area = RectF(bounds)
        val radius = 24f * density
        canvas.save()
        canvas.clipPath(Path().apply { addRoundRect(area, radius, radius, Path.Direction.CW) })
        paint.shader = LinearGradient(area.left, area.bottom, area.right, area.top,
            intArrayOf(Color.rgb(52, 56, 123), Color.rgb(94, 88, 171), Color.rgb(155, 177, 235)),
            null, Shader.TileMode.CLAMP)
        paint.alpha = opacity
        canvas.drawRect(area, paint)
        paint.shader = null
        // Oversized diagonal glass panes leave the title's left edge calm and readable.
        paint.color = Color.argb(30 * opacity / 255, 232, 238, 255)
        val w = area.width()
        val h = area.height()
        canvas.drawPath(Path().apply {
            moveTo(w * 0.73f, 0f); lineTo(w, 0f); lineTo(w * 0.66f, h); lineTo(w * 0.38f, h); close()
        }, paint)
        paint.color = Color.argb(25 * opacity / 255, 236, 244, 255)
        canvas.drawCircle(w * 0.97f, h * 0.13f, w * 0.3f, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = density
        paint.color = Color.argb(32 * opacity / 255, 236, 244, 255)
        for (index in 0..6) {
            val y = h * 0.65f + index * 22f * density
            canvas.drawLine(0f, y, w, y - h * 0.18f, paint)
            val x = index * w / 4f
            canvas.drawLine(x, h, x + w * 0.28f, h * 0.55f, paint)
        }
        paint.style = Paint.Style.FILL
        canvas.restore()
    }

    override fun setAlpha(alpha: Int) { opacity = alpha; invalidateSelf() }
    override fun setColorFilter(colorFilter: ColorFilter?) { paint.colorFilter = colorFilter; invalidateSelf() }
    @Deprecated("Deprecated in Android")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}
