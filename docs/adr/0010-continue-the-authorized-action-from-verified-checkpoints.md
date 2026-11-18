# Continue the authorized action from verified checkpoints

Status: accepted (2026-11-11); built and released (2026-11-18).

Both patchers will retain the player's exact approved action and verified completed work across interruption, recover consistency on reopen/reconnect, and continue that action. Discarding a valid snapshot or staged output repeats expensive work and fails the requested continuation; retention costs storage and requires complete content identities, durable ownership and consent boundaries. An unfinished snapshot/build restarts its stage, Stop safely revokes continuation while keeping reusable work, and new destructive consequences need fresh consent. Existing APK, pristine-delta and update-timing rules still apply. [Feature record](../features/automatic-continuation.md).
