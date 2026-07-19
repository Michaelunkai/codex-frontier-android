package com.michaelovsky.codexsubscription.isolated;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RuntimeWatchdogService extends Service {
    private static final String TAG = "CodexFrontierWatch";
    private static final String CHANNEL_ID = "codex_frontier_runtime";
    private static final String COMPLETION_CHANNEL_ID = "codex_frontier_turn_complete_v1";
    private static final int NOTIFICATION_ID = 5902;
    private static final int COMPLETION_NOTIFICATION_BASE_ID = 15902;
    private static final long HEALTH_INTERVAL_SECONDS = 15L;
    private static final long COMPLETION_INTERVAL_SECONDS = 2L;
    private static final long[] RETRY_DELAYS_MS = {0L, 2_000L, 5_000L, 10_000L, 30_000L, 60_000L};

    private final AtomicBoolean checking = new AtomicBoolean(false);
    private final AtomicBoolean checkingCompletions = new AtomicBoolean(false);
    private ScheduledExecutorService executor;
    private PowerManager.WakeLock wakeLock;
    private NotificationManager notificationManager;
    private volatile long nextStartAllowedAt;
    private volatile int consecutiveFailures;

    @Override public void onCreate() {
        super.onCreate();
        notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        createNotificationChannels();
        startForeground(NOTIFICATION_ID, buildNotification("Starting isolated runtime…", true));
        acquireWakeLock();
        executor = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "codex-frontier-watchdog");
            thread.setDaemon(true);
            return thread;
        });
        executor.scheduleWithFixedDelay(this::checkRuntimeSafely, 0L, HEALTH_INTERVAL_SECONDS, TimeUnit.SECONDS);
        executor.scheduleWithFixedDelay(this::checkCompletionsSafely, 1L, COMPLETION_INTERVAL_SECONDS, TimeUnit.SECONDS);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && RuntimeContract.ACTION_CHECK_NOW.equals(intent.getAction()) && executor != null) {
            executor.execute(this::checkRuntimeSafely);
        }
        return START_STICKY;
    }

    @Override public IBinder onBind(Intent intent) {
        return null;
    }

    @Override public void onDestroy() {
        if (executor != null) executor.shutdownNow();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    private void checkRuntimeSafely() {
        if (!checking.compareAndSet(false, true)) return;
        try {
            if (RuntimeContract.runtimeIsReady()) {
                consecutiveFailures = 0;
                nextStartAllowedAt = 0L;
                recordHealth(true, "ready");
                updateNotification("Ready · GPT-5.6 Sol · local port 5902", false);
                return;
            }

            consecutiveFailures += 1;
            recordHealth(false, "unreachable");
            long now = System.currentTimeMillis();
            if (now < nextStartAllowedAt) {
                updateNotification("Recovering runtime · retry scheduled", true);
                return;
            }

            updateNotification("Recovering isolated runtime…", true);
            requestRuntimeStart();
            int delayIndex = Math.min(consecutiveFailures, RETRY_DELAYS_MS.length - 1);
            nextStartAllowedAt = now + RETRY_DELAYS_MS[delayIndex];
        } catch (RuntimeException error) {
            Log.e(TAG, "Runtime health cycle failed", error);
            recordHealth(false, error.getClass().getSimpleName() + ": " + error.getMessage());
            updateNotification("Runtime recovery will retry automatically", true);
        } finally {
            checking.set(false);
        }
    }

    private void requestRuntimeStart() {
        Intent callback = new Intent(this, RuntimeCommandResultReceiver.class);
        int callbackFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 31) callbackFlags |= PendingIntent.FLAG_MUTABLE;
        PendingIntent resultIntent = PendingIntent.getBroadcast(
                this,
                (int) (System.currentTimeMillis() & 0x7fffffff),
                callback,
                callbackFlags);
        try {
            startService(RuntimeContract.createTermuxStartIntent(resultIntent));
            getSharedPreferences("runtime_watchdog", MODE_PRIVATE).edit()
                    .putLong("lastStartRequestedAt", System.currentTimeMillis())
                    .putInt("consecutiveFailures", consecutiveFailures)
                    .apply();
        } catch (RuntimeException error) {
            Log.e(TAG, "Termux RUN_COMMAND request failed", error);
            getSharedPreferences("runtime_watchdog", MODE_PRIVATE).edit()
                    .putLong("lastStartRequestedAt", System.currentTimeMillis())
                    .putString("lastStartError", error.getClass().getSimpleName() + ": " + error.getMessage())
                    .apply();
        }
    }

    private void recordHealth(boolean ready, String detail) {
        SharedPreferences preferences = getSharedPreferences("runtime_watchdog", MODE_PRIVATE);
        preferences.edit()
                .putBoolean("ready", ready)
                .putLong("lastHealthAt", System.currentTimeMillis())
                .putString("lastHealthDetail", detail)
                .putInt("consecutiveFailures", consecutiveFailures)
                .apply();
    }

    private void checkCompletionsSafely() {
        if (!checkingCompletions.compareAndSet(false, true)) return;
        try {
            SharedPreferences preferences = getSharedPreferences("runtime_watchdog", MODE_PRIVATE);
            boolean initialized = preferences.contains("lastCompletionSequence");
            long previousSequence = preferences.getLong("lastCompletionSequence", 0L);
            RuntimeContract.CompletionBatch batch = RuntimeContract.readCompletionEvents(previousSequence);
            if (batch == null) return;
            if (!initialized) {
                preferences.edit().putLong("lastCompletionSequence", batch.latestSequence).commit();
                return;
            }
            long recordedSequence = previousSequence;
            for (RuntimeContract.CompletionEvent event : batch.events) {
                if (event.sequence <= recordedSequence) continue;
                notifyTurnCompleted(event);
                recordedSequence = event.sequence;
                preferences.edit()
                        .putLong("lastCompletionSequence", recordedSequence)
                        .putString("lastCompletionTurnId", event.turnId)
                        .putString("lastCompletionStatus", event.status)
                        .putLong("lastCompletionAlertAt", System.currentTimeMillis())
                        .commit();
            }
            if (batch.latestSequence > recordedSequence && batch.events.isEmpty()) {
                preferences.edit().putLong("lastCompletionSequence", batch.latestSequence).commit();
            }
        } catch (RuntimeException error) {
            Log.e(TAG, "Completion notification cycle failed", error);
        } finally {
            checkingCompletions.set(false);
        }
    }

    private void notifyTurnCompleted(RuntimeContract.CompletionEvent event) {
        if (notificationManager == null) return;
        Intent openIntent = new Intent(this, MainActivity.class);
        openIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent open = PendingIntent.getActivity(this, (int) (event.sequence & 0x7fffffff), openIntent, flags);
        String normalizedStatus = event.status == null ? "completed" : event.status.trim().toLowerCase();
        String text = "completed".equals(normalizedStatus)
                ? "Your Codex session finished working."
                : "Your Codex session stopped: " + normalizedStatus + ".";
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, COMPLETION_CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(R.drawable.ic_codex_frontier_monochrome)
                .setContentTitle("Codex Frontier is ready")
                .setContentText(text)
                .setContentIntent(open)
                .setColor(Color.rgb(169, 144, 255))
                .setCategory(Notification.CATEGORY_STATUS)
                .setAutoCancel(true)
                .setOnlyAlertOnce(false)
                .setShowWhen(true)
                .setWhen(System.currentTimeMillis())
                .setPriority(Notification.PRIORITY_HIGH);
        if (Build.VERSION.SDK_INT < 26) {
            builder.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION));
            builder.setVibrate(new long[]{0L, 180L, 100L, 220L});
        }
        int notificationId = COMPLETION_NOTIFICATION_BASE_ID + (int) (event.sequence % 100000L);
        notificationManager.notify(notificationId, builder.build());
    }

    private void createNotificationChannels() {
        if (Build.VERSION.SDK_INT < 26 || notificationManager == null) return;
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Codex Frontier runtime",
                NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Keeps the isolated Codex subscription workspace ready after reboot.");
        channel.setShowBadge(false);
        channel.enableLights(false);
        channel.enableVibration(false);
        notificationManager.createNotificationChannel(channel);

        NotificationChannel completionChannel = new NotificationChannel(
                COMPLETION_CHANNEL_ID,
                "Finished Codex sessions",
                NotificationManager.IMPORTANCE_HIGH);
        completionChannel.setDescription("Plays a notification sound whenever a Codex Frontier turn finishes or stops.");
        completionChannel.setShowBadge(true);
        completionChannel.enableLights(true);
        completionChannel.setLightColor(Color.rgb(169, 144, 255));
        completionChannel.enableVibration(true);
        completionChannel.setVibrationPattern(new long[]{0L, 180L, 100L, 220L});
        Uri sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
        AudioAttributes audioAttributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
        completionChannel.setSound(sound, audioAttributes);
        notificationManager.createNotificationChannel(completionChannel);
    }

    private Notification buildNotification(String text, boolean ongoingWork) {
        Intent openIntent = new Intent(this, MainActivity.class);
        openIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent open = PendingIntent.getActivity(this, 5902, openIntent, flags);

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(R.drawable.ic_codex_frontier_monochrome)
                .setContentTitle("Codex Frontier")
                .setContentText(text)
                .setContentIntent(open)
                .setColor(Color.rgb(79, 209, 255))
                .setCategory(Notification.CATEGORY_SERVICE)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setPriority(ongoingWork ? Notification.PRIORITY_LOW : Notification.PRIORITY_MIN);
        return builder.build();
    }

    private void updateNotification(String text, boolean ongoingWork) {
        if (notificationManager != null) {
            notificationManager.notify(NOTIFICATION_ID, buildNotification(text, ongoingWork));
        }
    }

    private void acquireWakeLock() {
        PowerManager manager = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (manager == null) return;
        wakeLock = manager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "CodexFrontier:RuntimeWatchdog");
        wakeLock.setReferenceCounted(false);
        wakeLock.acquire();
    }
}
