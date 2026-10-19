package dev.halixm.hokacepatcher

import android.content.Context
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

/** The hero panel (DESIGN.md): the panel gradient and a few faint diagonal light bands, drawn locally. */
class AceHeroDrawable(context: Context) : Drawable() {
    private val density = context.resources.displayMetrics.density
    private val radius = context.resources.getDimension(R.dimen.corner_card)
    private val top = context.getColor(R.color.panel_top)
    private val bottom = context.getColor(R.color.panel_bottom)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var opacity = 255

    override fun draw(canvas: Canvas) {
        val area = RectF(bounds)
        canvas.save()
        canvas.clipPath(Path().apply { addRoundRect(area, radius, radius, Path.Direction.CW) })
        paint.shader = LinearGradient(area.left, area.top, area.left, area.bottom, top, bottom, Shader.TileMode.CLAMP)
        paint.alpha = opacity
        canvas.drawRect(area, paint)
        paint.shader = null
        // Oversized diagonal bands leave the title's left edge calm and readable.
        paint.color = Color.argb(22 * opacity / 255, 255, 255, 255)
        val w = area.width()
        val h = area.height()
        canvas.drawPath(Path().apply {
            moveTo(w * 0.73f, 0f); lineTo(w, 0f); lineTo(w * 0.66f, h); lineTo(w * 0.38f, h); close()
        }, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = density
        paint.color = Color.argb(26 * opacity / 255, 255, 255, 255)
        for (index in 0..3) {
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
