package org.firetools.adshelper;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.Settings;

final class HelperSettings implements AdsState.Storage, AdsState.Setting {
    private static final String KEY = "LOCKSCREEN_AD_ENABLED";
    private static final String ENABLED = "enabled";
    private static final String SAVED = "original_saved";
    private static final String PRESENT = "original_present";
    private static final String ORIGINAL = "original_value";
    private static final String STATUS = "status";

    private final Context context;
    final SharedPreferences preferences;

    HelperSettings(Context context) {
        this.context = context;
        preferences = context.getSharedPreferences("ads_helper", Context.MODE_PRIVATE);
    }

    AdsState state() {
        return new AdsState(this, this);
    }

    boolean canWriteSettings() {
        return context.checkSelfPermission("android.permission.WRITE_SECURE_SETTINGS")
                == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    public boolean isEnabled() {
        return preferences.getBoolean(ENABLED, false);
    }

    @Override
    public void setEnabled(boolean enabled) {
        if (!preferences.edit().putBoolean(ENABLED, enabled).commit()) {
            throw new IllegalStateException("Unable to save the helper's enabled state.");
        }
    }

    @Override
    public boolean hasOriginal() {
        return preferences.getBoolean(SAVED, false);
    }

    @Override
    public AdsState.Entry originalValue() {
        return new AdsState.Entry(preferences.getBoolean(PRESENT, false), preferences.getString(ORIGINAL, null));
    }

    @Override
    public void saveOriginal(AdsState.Entry entry) {
        if (!writeBackup(preferences.edit(), entry).commit()) {
            removeBackup(preferences.edit()).apply();
            throw new IllegalStateException("Unable to save the original setting.");
        }
    }

    @Override
    public void clearOriginal() {
        AdsState.Entry original = originalValue();
        if (!removeBackup(preferences.edit()).commit()) {
            writeBackup(preferences.edit(), original).apply();
            throw new IllegalStateException("The setting was restored, but its backup could not be cleared.");
        }
    }

    private SharedPreferences.Editor writeBackup(SharedPreferences.Editor editor, AdsState.Entry entry) {
        return editor.putBoolean(SAVED, true).putBoolean(PRESENT, entry.present).putString(ORIGINAL, entry.value);
    }

    private SharedPreferences.Editor removeBackup(SharedPreferences.Editor editor) {
        return editor.remove(SAVED).remove(PRESENT).remove(ORIGINAL);
    }

    @Override
    public String read() {
        return Settings.Global.getString(context.getContentResolver(), KEY);
    }

    @Override
    public AdsState.Entry snapshot() {
        try (Cursor original = context.getContentResolver().query(Settings.Global.getUriFor(KEY),
                new String[]{Settings.NameValueTable.VALUE}, null, null, null)) {
            if (original == null) {
                throw new IllegalStateException("Android did not return the setting's current state.");
            }
            return original.moveToFirst() ? new AdsState.Entry(true, original.getString(0))
                    : new AdsState.Entry(false, null);
        }
    }

    @Override
    public boolean write(String value) {
        return Settings.Global.putString(context.getContentResolver(), KEY, value);
    }

    @Override
    public void delete() {
        context.getContentResolver().delete(Settings.Global.getUriFor(KEY), null, null);
    }

    String status() {
        return preferences.getString(STATUS, "");
    }

    void status(String message) {
        preferences.edit().putString(STATUS, message).apply();
    }

    String errorMessage(String operation, RuntimeException error) {
        if (error instanceof SecurityException) {
            return operation + " Android denied permission to complete the operation.";
        }
        String detail = error.getMessage();
        return operation + (detail == null ? " " + error.getClass().getSimpleName() : " " + detail);
    }
}
