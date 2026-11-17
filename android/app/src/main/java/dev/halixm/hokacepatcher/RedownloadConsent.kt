package dev.halixm.hokacepatcher

import org.json.JSONArray
import org.json.JSONObject

/**
 * The scoped Re-download of a saved action (ticket 12): one exact deletion plan, by the digest of its
 * `plan.json` ([planSha256]) in the session's `redownload-plans/<planId>/`. Since the user's decision of
 * 2026-11-13 the coordinator approves a measured plan itself ([approvalSource] `automatic`,
 * [RedownloadConsent.automaticAllowed]) once per package per run; the user's own approval for that same
 * digest ([approvalSource] `user`) remains for a plan the loop guard holds back. A changed plan needs a new
 * approval. [state] is one of [RedownloadConsent.STATES]; an approval ([approvalId]) exists exactly from
 * `approved` on.
 */
data class Redownload(val planId: String, val planSha256: String, val files: Int, val packages: List<String>,
                      val bytes: Long, val state: String, val approvalId: String?, val approvedMs: Long?,
                      val approvalSource: String? = null,
                      /** An approval saved before automatic Re-download, without `source`: it was the user's. */
                      val legacyApproval: Boolean = false) {
    /** Approved for deletion and not yet consumed by a completed deletion. */
    val approved: Boolean get() = state in setOf(RedownloadConsent.APPROVED, RedownloadConsent.DELETING) && approvalId != null
    /** The user has not answered, or declined: nothing may be deleted. */
    val needsAnswer: Boolean get() = state in setOf(RedownloadConsent.AWAITING, RedownloadConsent.DECLINED)
}

/**
 * Re-download consent rules: every state change of a [Redownload] and the record it is saved as. Pure: it
 * takes and returns values. [RunStore] persists each result under its lock, checks the run may continue,
 * and owns the retry state an approval re-arms.
 */
object RedownloadConsent {
    /** Waiting for the user to answer this exact plan; nothing is deleted. */
    const val AWAITING = "awaiting_consent"
    /** The user declined this exact plan: no deletion, and no automatic prompt for it again. */
    const val DECLINED = "declined"
    /** Approved for exactly this plan; no file deleted yet. */
    const val APPROVED = "approved"
    /** Saved before the first deletion of the approved plan; an interrupted run resumes it without asking. */
    const val DELETING = "deleting"
    /** The plan's files are deleted (the approval is consumed); the game must download them before translation. */
    const val DELETED = "deleted"
    /** The user said the game's download finished; the saved action continues and checks readiness itself. */
    const val DOWNLOADS_CONFIRMED = "downloads_confirmed"
    @JvmField val STATES = setOf(AWAITING, DECLINED, APPROVED, DELETING, DELETED, DOWNLOADS_CONFIRMED)
    /** The logical operation of the deletions; a new approval, never an explicit Retry, re-arms it. */
    const val DELETE_OPERATION = "redownload_delete"
    /** Who approved a plan: the coordinator (user decision 2026-11-13) or the user's review. */
    const val APPROVAL_AUTOMATIC = "automatic"
    const val APPROVAL_USER = "user"

    private val HASH = Regex("[0-9a-f]{64}")
    private val PACKAGE = Regex("[0-9]{1,20}")
    /** A plan with this digest in these states was consumed: proposing it again starts a new unanswered plan. */
    private val CONSUMED = setOf(DELETED, DOWNLOADS_CONFIRMED)

    /**
     * The loop guard of automatic Re-download (user decision 2026-11-13): the coordinator approves a freshly
     * proposed plan ([state] `awaiting_consent`) only while its deletion budget is unspent ([deleteAttempts]
     * under 2: two interrupted deletions wait for the user) and none of its [packages] was already deleted in
     * this run ([redownloaded], [RunStore.Run.redownloadedPackages]). A package the game still cannot update
     * after its own download is never deleted again by itself; it waits for the user's review. A declined plan
     * stays declined.
     */
    @JvmStatic
    fun automaticAllowed(state: String?, deleteAttempts: Int, redownloaded: Collection<String>,
                         packages: Collection<String>): Boolean =
        state == AWAITING && deleteAttempts < 2 && packages.isNotEmpty() && packages.none { it in redownloaded }

    /**
     * A confirmed Re-download download counts as the user's source-download answer only for this run's own
     * deletion: the run may continue, its plan is in [DOWNLOADS_CONFIRMED], and that plan is the last one the
     * session journal records as deleted ([deletedPlanSha256]). Anything else (a declined, approved,
     * still-deleting or unconfirmed plan, another plan's deletion, a stopped run) answers nothing.
     */
    @JvmStatic
    fun answersSourceDownloads(mayContinue: Boolean, redownload: Redownload?, deletedPlanSha256: String?): Boolean =
        mayContinue && redownload != null && redownload.state == DOWNLOADS_CONFIRMED &&
            deletedPlanSha256 != null && HASH.matches(deletedPlanSha256) && redownload.planSha256 == deletedPlanSha256

    /**
     * The exact plan a damaged-file refusal produced. The same digest keeps its answer (an approval resumes
     * without asking, a decline does not ask again), and only the plan's folder ([Redownload.planId]) follows
     * the newest copy. A different digest, or any plan after a consumed approval, replaces it unanswered: a
     * changed or larger scope always needs a new approval.
     */
    fun proposed(current: Redownload?, planId: String, planSha256: String, files: Int, packages: List<String>,
                 bytes: Long): Redownload =
        if (current != null && current.planSha256 == planSha256 && current.state !in CONSUMED) current.copy(planId = planId)
        else Redownload(planId, planSha256, files, packages, bytes, AWAITING, null, null)

    /** [plan] approved as [source], with a fresh approval [approvalId] at [nowMs]. A new destructive attempt scope. */
    fun approved(plan: Redownload, source: String, approvalId: String, nowMs: Long): Redownload {
        require(source == APPROVAL_AUTOMATIC || source == APPROVAL_USER)
        return plan.copy(state = APPROVED, approvalId = approvalId, approvedMs = nowMs, approvalSource = source,
            legacyApproval = false)
    }

    /** The saved plan the user's answer is for: exactly [planSha256], and not yet answered. */
    fun answerable(current: Redownload?, planSha256: String): Redownload {
        val plan = checkNotNull(current) { "No Re-download plan waits for approval" }
        check(plan.planSha256 == planSha256) { "The Re-download plan changed; review it again" }
        check(plan.needsAnswer) { "This Re-download plan was already answered" }
        return plan
    }

    /** The user declined (or dismissed) the plan: nothing is deleted, and it is not asked again by itself. */
    fun declined(current: Redownload?, planSha256: String): Redownload =
        answerable(current, planSha256).copy(state = DECLINED)

    /**
     * Progress of the approved plan [planSha256]. `deleting` is saved before the first deletion (approved or
     * deleting plans of a run that [mayContinue] only); `deleted` once its files and Watchdog are gone (it
     * records what happened, even after a Stop); a readiness refusal after the downloads answer goes back to
     * `deleted`.
     */
    fun progressed(current: Redownload?, planSha256: String, state: String, mayContinue: Boolean): Redownload {
        val plan = checkNotNull(current) { "No Re-download plan" }
        check(plan.planSha256 == planSha256) { "Re-download plan differs" }
        val allowed = when (state) {
            DELETING -> mayContinue && plan.approved
            DELETED -> plan.state in setOf(DELETING, DELETED, DOWNLOADS_CONFIRMED)
            else -> false
        }
        check(allowed) { "Invalid Re-download progress" }
        return plan.copy(state = state)
    }

    /** The approved plan's deletion budget is spent: the same exact plan waits for a fresh answer. */
    fun awaitingFreshConsent(current: Redownload?, planSha256: String): Redownload {
        val plan = checkNotNull(current) { "No Re-download plan" }
        check(plan.planSha256 == planSha256 && plan.approved) { "Re-download plan differs" }
        return plan.copy(state = AWAITING, approvalId = null, approvedMs = null, approvalSource = null, legacyApproval = false)
    }

    /** The user's answer that the game finished downloading the deleted files. */
    fun downloadsConfirmed(current: Redownload?): Redownload {
        check(current?.state == DELETED) { "No Re-download waits for the game's download" }
        return current!!.copy(state = DOWNLOADS_CONFIRMED)
    }

    /** Reject a saved `redownload` record that is malformed, out of bounds or inconsistent with its state. */
    fun validate(value: JSONObject) {
        fields(value, setOf("plan_id", "plan_sha256", "files", "packages", "bytes", "state", "approval"))
        for (name in listOf("plan_id", "plan_sha256", "state")) check(value.get(name) is String)
        GameFilePolicy.session(value.getString("plan_id"))
        check(HASH.matches(value.getString("plan_sha256")) && value.getString("state") in STATES)
        check(integer(value, "files") in 1L..8192L && integer(value, "bytes") in 0L..(64L * 1024 * 1024 * 1024))
        val packages = value.get("packages"); check(packages is JSONArray && packages.length() in 1..1024)
        val names = (0 until packages.length()).map { val name = packages.get(it); check(name is String && PACKAGE.matches(name)); name as String }
        check(names.toSet().size == names.size) { "Duplicate Re-download package" }
        val approved = value.getString("state") !in setOf(AWAITING, DECLINED)
        if (value.isNull("approval")) check(!approved) { "An approved Re-download needs its approval" } else {
            check(approved) { "An unanswered Re-download cannot carry an approval" }
            val approval = value.get("approval"); check(approval is JSONObject)
            // `source` is absent on approvals saved before automatic Re-download (2026-11-13): those were the user's.
            fields(approval, setOf("id", "approved_ms") + approval.keys().asSequence().filter { it == "source" })
            check(approval.get("id") is String)
            GameFilePolicy.session(approval.getString("id")); check(integer(approval, "approved_ms") > 0)
            if (approval.has("source")) check(approval.get("source") in setOf(APPROVAL_AUTOMATIC, APPROVAL_USER))
        }
    }

    /** The [Redownload] a validated record describes. */
    fun decode(value: JSONObject): Redownload {
        val packages = value.getJSONArray("packages")
        val approval = value.optJSONObject("approval")
        return Redownload(value.getString("plan_id"), value.getString("plan_sha256"), value.getInt("files"),
            (0 until packages.length()).map { packages.getString(it) }, value.getLong("bytes"), value.getString("state"),
            approval?.getString("id"), approval?.getLong("approved_ms"),
            approval?.let { if (it.has("source")) it.getString("source") else APPROVAL_USER },
            approval != null && !approval.has("source"))
    }

    /** The record [plan] is saved as; a legacy approval keeps its original shape, without `source`. */
    fun encode(plan: Redownload): JSONObject {
        val approval: Any = if (plan.approvalId == null) JSONObject.NULL else JSONObject()
            .put("id", plan.approvalId).put("approved_ms", checkNotNull(plan.approvedMs))
            .also { if (!plan.legacyApproval) it.put("source", checkNotNull(plan.approvalSource)) }
        return JSONObject().put("plan_id", plan.planId).put("plan_sha256", plan.planSha256).put("files", plan.files)
            .put("packages", JSONArray(plan.packages)).put("bytes", plan.bytes).put("state", plan.state)
            .put("approval", approval)
    }

    private fun fields(value: JSONObject, expected: Set<String>) {
        check(value.keys().asSequence().toSet() == expected) { "Unknown or missing run fields" }
    }
    private fun integer(value: JSONObject, key: String): Long {
        val raw = value.get(key); check(raw is Int || raw is Long) { "Expected integer $key" }; return (raw as Number).toLong()
    }
}
