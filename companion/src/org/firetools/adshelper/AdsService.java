package org.firetools.adshelper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

public final class AdsService extends Service {
    private static final String CHANNEL = "ads_helper_active";
    private static final String ACTION_STOP = "org.firetools.adshelper.STOP_FROM_NOTIFICATION";
    private static final int NOTIFICATION_ID = 1;
    private static final long CHECK_INTERVAL_MS = 4000;

    // Activity, service, and receivers all run in the same process and on its main thread.
    static boolean running;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable check = this::applySetting;
    private final BroadcastReceiver screenReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (Intent.ACTION_SCREEN_ON.equals(intent.getAction())) {
                applySetting();
            }
        }
    };

    private HelperSettings settings;
    private boolean screenReceiverRegistered;

    static void start(Context context) {
        createChannel(context);
        if (!canShowNotification(context)) {
            throw new IllegalStateException("Allow the helper notification in Android settings to continue.");
        }
        Intent intent = new Intent(context, AdsService.class);
        if ((Build.VERSION.SDK_INT >= 26 ? context.startForegroundService(intent)
                : context.startService(intent)) == null) {
            throw new IllegalStateException("Android did not start the helper service.");
        }
    }

    static void createChannel(Context context) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL, "Ads helper activity", NotificationManager.IMPORTANCE_LOW);
            context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    private static boolean canShowNotification(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null || !manager.areNotificationsEnabled()) {
            return false;
        }
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = manager.getNotificationChannel(CHANNEL);
            return channel != null && channel.getImportance() != NotificationManager.IMPORTANCE_NONE;
        }
        return true;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        settings = new HelperSettings(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            createChannel(this);
            startForeground(NOTIFICATION_ID, notification());
            if (intent != null && ACTION_STOP.equals(intent.getAction())) {
                settings.state().stop();
                settings.status("Stopped. Use Restore to apply the saved setting.");
                finishService();
                return START_NOT_STICKY;
            }
            if (!screenReceiverRegistered) {
                registerReceiver(screenReceiver, new IntentFilter(Intent.ACTION_SCREEN_ON));
                screenReceiverRegistered = true;
            }
            applySetting();
            return running ? START_STICKY : START_NOT_STICKY;
        } catch (RuntimeException error) {
            fail(error);
            return START_NOT_STICKY;
        }
    }

    private void applySetting() {
        handler.removeCallbacks(check);
        if (!settings.isEnabled()) {
            finishService();
            return;
        }
        try {
            if (!settings.canWriteSettings()) {
                throw new IllegalStateException("The ADB permission is missing.");
            }
            if (!canShowNotification(this)) {
                throw new IllegalStateException("The helper notification is disabled.");
            }
            settings.state().apply();
            if (!running) {
                running = true;
                settings.status("The last check read 0. Fire OS controls whether ads are shown.");
            }
            handler.postDelayed(check, CHECK_INTERVAL_MS);
        } catch (RuntimeException error) {
            fail(error);
        }
    }

    private void fail(RuntimeException error) {
        String message = settings.errorMessage("The helper stopped.", error);
        try {
            settings.state().stop();
        } catch (RuntimeException saveError) {
            message = settings.errorMessage(message, saveError);
        }
        settings.status(message);
        finishService();
    }

    private void finishService() {
        running = false;
        handler.removeCallbacks(check);
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @SuppressWarnings("deprecation")
    private Notification notification() {
        Intent open = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent openApp = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, AdsService.class).setAction(ACTION_STOP);
        PendingIntent stopService = PendingIntent.getService(this, 0, stop, PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        return builder.setSmallIcon(android.R.drawable.ic_lock_idle_lock)
                .setContentTitle("Fire Tools Ads Helper")
                .setContentText("Checking the lock-screen ads setting")
                .setContentIntent(openApp)
                .setDeleteIntent(stopService)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Stop", stopService).build())
                .build();
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(check);
        if (screenReceiverRegistered) {
            unregisterReceiver(screenReceiver);
        }
        if (running) {
            running = false;
            if (settings.isEnabled()) {
                settings.status("Android stopped the service. Open the helper to restart it.");
            }
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
