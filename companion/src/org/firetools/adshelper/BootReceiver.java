package org.firetools.adshelper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        HelperSettings settings = new HelperSettings(context);
        if (!settings.isEnabled()) {
            return;
        }
        if (!settings.canWriteSettings()) {
            settings.status("Boot resume skipped. The ADB permission is missing.");
            return;
        }
        try {
            AdsService.start(context);
        } catch (RuntimeException error) {
            settings.status(settings.errorMessage("Boot resume failed. Open the helper to retry.", error));
        }
    }
}
