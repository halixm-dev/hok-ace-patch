// SPAKE2 for ADB pairing, ported from Shizuku's manager/src/main/jni/adb_pairing.cpp
// (Copyright RikkaW, Apache-2.0), itself following AOSP's adb/pairing_auth. Only the SPAKE2
// exchange lives here; the key derivation and the cipher are in AdbPairing.kt.
#include <jni.h>
#include <cstring>
#include <openssl/curve25519.h>

namespace {

// The names include their NUL: adbd passes them with sizeof.
const uint8_t kClientName[] = "adb pair client";
const uint8_t kServerName[] = "adb pair server";

struct Spake2 {
    SPAKE2_CTX *ctx;
    uint8_t msg[SPAKE2_MAX_MSG_SIZE];
    size_t msg_size;
};

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_dev_halixm_hokacepatcher_AdbSpake2_nativeCreate(JNIEnv *env, jclass, jbyteArray jPassword) {
    SPAKE2_CTX *ctx = SPAKE2_CTX_new(spake2_role_alice, kClientName, sizeof(kClientName),
                                     kServerName, sizeof(kServerName));
    if (ctx == nullptr) return 0;
    auto *state = new Spake2{ctx, {}, 0};
    jsize size = env->GetArrayLength(jPassword);
    jbyte *password = env->GetByteArrayElements(jPassword, nullptr);
    int ok = SPAKE2_generate_msg(ctx, state->msg, &state->msg_size, sizeof(state->msg),
                                 reinterpret_cast<uint8_t *>(password), static_cast<size_t>(size));
    env->ReleaseByteArrayElements(jPassword, password, JNI_ABORT);
    if (ok != 1 || state->msg_size == 0) {
        SPAKE2_CTX_free(ctx);
        delete state;
        return 0;
    }
    return reinterpret_cast<jlong>(state);
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_dev_halixm_hokacepatcher_AdbSpake2_nativeMessage(JNIEnv *env, jclass, jlong pointer) {
    auto *state = reinterpret_cast<Spake2 *>(pointer);
    jbyteArray out = env->NewByteArray(static_cast<jsize>(state->msg_size));
    env->SetByteArrayRegion(out, 0, static_cast<jsize>(state->msg_size), reinterpret_cast<jbyte *>(state->msg));
    return out;
}

// The shared key material for <jTheirs>, or null when their message does not process.
extern "C" JNIEXPORT jbyteArray JNICALL
Java_dev_halixm_hokacepatcher_AdbSpake2_nativeProcess(JNIEnv *env, jclass, jlong pointer, jbyteArray jTheirs) {
    auto *state = reinterpret_cast<Spake2 *>(pointer);
    jsize size = env->GetArrayLength(jTheirs);
    if (size > static_cast<jsize>(SPAKE2_MAX_MSG_SIZE)) return nullptr;
    jbyte *theirs = env->GetByteArrayElements(jTheirs, nullptr);
    uint8_t key[SPAKE2_MAX_KEY_SIZE];
    size_t key_size = 0;
    int ok = SPAKE2_process_msg(state->ctx, key, &key_size, sizeof(key),
                                reinterpret_cast<uint8_t *>(theirs), static_cast<size_t>(size));
    env->ReleaseByteArrayElements(jTheirs, theirs, JNI_ABORT);
    if (ok != 1) return nullptr;
    jbyteArray out = env->NewByteArray(static_cast<jsize>(key_size));
    env->SetByteArrayRegion(out, 0, static_cast<jsize>(key_size), reinterpret_cast<jbyte *>(key));
    memset(key, 0, sizeof(key));
    return out;
}

extern "C" JNIEXPORT void JNICALL
Java_dev_halixm_hokacepatcher_AdbSpake2_nativeFree(JNIEnv *, jclass, jlong pointer) {
    auto *state = reinterpret_cast<Spake2 *>(pointer);
    SPAKE2_CTX_free(state->ctx);
    delete state;
}
