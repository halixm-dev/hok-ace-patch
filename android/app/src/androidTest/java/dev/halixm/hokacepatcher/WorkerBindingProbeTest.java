package dev.halixm.hokacepatcher;

import android.content.Context;
import android.content.pm.PackageManager;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.json.JSONObject;
import org.junit.Test;
import rikka.shizuku.Shizuku;
import static org.junit.Assert.*;

/** Real shell-service ownership and death; only diagnostics and own-service destruction. */
public final class WorkerBindingProbeTest {
    private Context ready() throws Exception {
        CountDownLatch available = new CountDownLatch(1);
        Shizuku.OnBinderReceivedListener listener = available::countDown;
        Shizuku.addBinderReceivedListenerSticky(listener);
        try { assertTrue(available.await(15, TimeUnit.SECONDS)); }
        finally { Shizuku.removeBinderReceivedListener(listener); }
        assertEquals(PackageManager.PERMISSION_GRANTED, Shizuku.checkSelfPermission());
        return InstrumentationRegistry.getInstrumentation().getTargetContext();
    }
    @Test public void testClosingOneOwnerCannotDestroyTheNextBinding() throws Exception {
        Context context = ready();
        AtomicInteger lost = new AtomicInteger();
        try (WorkerDeviceConnection first = WorkerDeviceConnection.Companion.open(context, ShellProvider.SHIZUKU, () -> { lost.incrementAndGet(); return kotlin.Unit.INSTANCE; });
             WorkerDeviceConnection second = WorkerDeviceConnection.Companion.open(context, ShellProvider.SHIZUKU, () -> { lost.incrementAndGet(); return kotlin.Unit.INSTANCE; })) {
            assertEquals(2000, new JSONObject(first.await().diagnostics()).getInt("uid"));
            IPrivilegedDeviceService next = second.await();
            first.close(); first.close();
            long before = System.nanoTime();
            try { first.await(); fail("Closed owner returned its service"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("closed")); }
            assertTrue(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before) < 1000);
            Thread.sleep(300);
            assertEquals(2000, new JSONObject(next.diagnostics()).getInt("uid"));
            assertEquals(0, lost.get());
        }
        assertEquals(0, lost.get());
    }
    @Test public void testUserServiceDeathWakesWaitersAndCannotReconnect() throws Exception {
        Context context = ready();
        AtomicInteger lost = new AtomicInteger(); CountDownLatch died = new CountDownLatch(1);
        try (WorkerDeviceConnection owner = WorkerDeviceConnection.Companion.open(context, ShellProvider.SHIZUKU, () -> {
            lost.incrementAndGet(); died.countDown(); return kotlin.Unit.INSTANCE;
        })) {
            IPrivilegedDeviceService service = owner.await();
            assertEquals(2000, new JSONObject(service.diagnostics()).getInt("uid"));
            try { service.destroy(); } catch (Exception expectedDeath) { }
            assertTrue(died.await(10, TimeUnit.SECONDS));
            long before = System.nanoTime();
            try { owner.await(); fail("Lost worker accepted work"); }
            catch (IllegalStateException expected) { assertTrue(expected.getMessage().contains("disconnected")); }
            assertTrue(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before) < 1000);
            Thread.sleep(300); assertEquals(1, lost.get());
            owner.close(); owner.close(); assertEquals(1, lost.get());
        }
    }
}
