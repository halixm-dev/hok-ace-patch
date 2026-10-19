package dev.halixm.hokacepatcher

import android.app.AlertDialog
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.TextView

/**
 * DESIGN.md's plain confirmation dialog: a deep-indigo panel, the heading in `on-panel`, the message
 * in `on-panel-muted`, the ice-blue confirm button on the right and a secondary Cancel on the left.
 * Call after `show()`, once the dialog's views exist.
 */
object PanelDialog {
    fun style(dialog: AlertDialog) {
        val context = dialog.context
        val resources = context.resources
        val density = resources.displayMetrics.density
        val corner = resources.getDimension(R.dimen.corner_card)
        val buttonCorner = resources.getDimension(R.dimen.corner_button)
        dialog.window?.setBackgroundDrawable(GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(context.getColor(R.color.panel_top), context.getColor(R.color.panel_bottom))).apply {
                cornerRadius = corner
            })
        val title = resources.getIdentifier("alertTitle", "id", "android")
        dialog.findViewById<TextView>(title)?.apply {
            setTextColor(context.getColor(R.color.on_panel))
            setTextSize(TypedValue.COMPLEX_UNIT_PX, resources.getDimension(R.dimen.type_heading))
            typeface = resources.getFont(R.font.barlow_bold)
            isAccessibilityHeading = true
        }
        dialog.findViewById<TextView>(android.R.id.message)?.apply {
            setTextColor(context.getColor(R.color.on_panel_muted))
            setTextSize(TypedValue.COMPLEX_UNIT_PX, resources.getDimension(R.dimen.type_body))
            typeface = resources.getFont(R.font.barlow_regular)
        }
        val disabled = intArrayOf(-android.R.attr.state_enabled)
        dialog.window?.decorView?.let { checkboxes(it).forEach(::checkbox) }
        fun button(view: Button?, fill: GradientDrawable, textColor: Int) = view?.apply {
            isAllCaps = false
            typeface = resources.getFont(R.font.barlow_semibold)
            setTextSize(TypedValue.COMPLEX_UNIT_PX, resources.getDimension(R.dimen.type_button))
            setTextColor(ColorStateList(arrayOf(disabled, intArrayOf()),
                intArrayOf(context.getColor(R.color.disabled_text), context.getColor(textColor))))
            background = StateListDrawable().apply {
                addState(disabled, GradientDrawable().apply {
                    setColor(context.getColor(R.color.disabled_fill)); cornerRadius = buttonCorner
                })
                addState(intArrayOf(), fill)
            }
            val pad = (12 * density).toInt()
            setPadding(pad, 0, pad, 0)
        }
        button(dialog.getButton(AlertDialog.BUTTON_POSITIVE), GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT,
            intArrayOf(context.getColor(R.color.confirm_left), context.getColor(R.color.confirm_right))).apply {
                cornerRadius = buttonCorner
            }, R.color.ink)
        val ink = context.getColor(R.color.ink)
        button(dialog.getButton(AlertDialog.BUTTON_NEGATIVE), GradientDrawable().apply {
            setColor(context.getColor(R.color.card)); cornerRadius = buttonCorner
            setStroke((1 * density).toInt(), Color.argb(77, Color.red(ink), Color.green(ink), Color.blue(ink)))
        }, R.color.ink)
    }

    private fun checkboxes(view: View): List<CheckBox> = when (view) {
        is CheckBox -> listOf(view)
        is ViewGroup -> (0 until view.childCount).flatMap { checkboxes(view.getChildAt(it)) }
        else -> emptyList()
    }

    /** A consent checkbox keeps its unchecked default; only its colours change. */
    private fun checkbox(view: CheckBox) {
        val context = view.context
        view.setTextColor(context.getColor(R.color.on_panel))
        view.typeface = context.resources.getFont(R.font.barlow_regular)
        view.buttonTintList = ColorStateList.valueOf(context.getColor(R.color.on_panel))
    }
}
