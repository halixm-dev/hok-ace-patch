package dev.halixm.hokacepatcher

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/** Code-drawn phone, saved file and translation picture; no network or downloaded artwork. */
class StepPicture(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    init {
        val pictureHeight = (80 * resources.displayMetrics.density).toInt()
        minimumHeight = pictureHeight
        layoutParams = android.widget.LinearLayout.LayoutParams(-1, pictureHeight)
        contentDescription = "Phone, saved recovery copy, English translation. Follow the numbered steps below."
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.save(); canvas.scale(width / 300f, height / 96f)
        paint.color = Color.rgb(25, 81, 161); paint.style = Paint.Style.STROKE; paint.strokeWidth = 3f
        canvas.drawRoundRect(15f, 10f, 59f, 76f, 7f, 7f, paint)
        canvas.drawLine(29f, 66f, 45f, 66f, paint)
        canvas.drawRoundRect(126f, 19f, 170f, 68f, 3f, 3f, paint)
        canvas.drawLine(137f, 33f, 159f, 33f, paint)
        canvas.drawLine(137f, 44f, 159f, 44f, paint)
        canvas.drawRoundRect(230f, 16f, 286f, 69f, 12f, 12f, paint)
        for (x in listOf(82f, 191f)) {
            canvas.drawLine(x, 43f, x + 22f, 43f, paint)
            canvas.drawPath(Path().apply { moveTo(x + 15f, 36f); lineTo(x + 22f, 43f); lineTo(x + 15f, 50f) }, paint)
        }
        paint.style = Paint.Style.FILL; paint.textSize = 18f; paint.textAlign = Paint.Align.CENTER
        canvas.drawText("EN", 258f, 49f, paint)
        canvas.restore()
    }
}
