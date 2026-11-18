package dev.halixm.hokacepatcher

import org.json.JSONArray
import org.json.JSONObject

/**
 * A retired snapshot (`snapshot-attempts/<id>/retired`) no longer matches the live layer, so it is never a
 * rollback base, a reusable checkpoint or a Re-download plan's bytes: a plan binds only the manifest digest
 * and is checked against the canonical snapshot. A measured shortage may release its bytes. The journal keeps
 * `retired_snapshots` as history and lists released ids in `retired_released`.
 */
object RetiredSnapshots {
    const val RELEASED = "retired_released"

    /**
     * The attempt ids of retired snapshots whose bytes a measured shortage may release from the saved journal
     * <saved>: listed in `retired_snapshots`, not yet in `retired_released`, never the current
     * `snapshot_attempt`, and only while no game file is mid-change (no dirty packages, no mutation intent,
     * no verified payload), the same state in which a snapshot may be retired. Malformed ids are skipped.
     */
    fun releasable(saved: JSONObject): List<String> {
        if (saved.optBoolean("packages_dirty", false) || !saved.isNull("mutation_intent") ||
            saved.optBoolean("patch_payload_verified", false)) return emptyList()
        val history = saved.optJSONArray("retired_snapshots") ?: return emptyList()
        val released = ids(saved.optJSONArray(RELEASED))
        val current = saved.optString("snapshot_attempt")
        return ids(history).filter { id ->
            id !in released && id != current && runCatching { GameFilePolicy.session(id) }.isSuccess
        }.distinct()
    }

    /** The `retired_released` list with <id> added once. */
    fun released(saved: JSONObject, id: String): JSONArray {
        val list = saved.optJSONArray(RELEASED) ?: JSONArray()
        if (id !in ids(list)) list.put(id)
        return list
    }

    private fun ids(array: JSONArray?): List<String> =
        (0 until (array?.length() ?: 0)).mapNotNull { array?.opt(it) as? String }
}
