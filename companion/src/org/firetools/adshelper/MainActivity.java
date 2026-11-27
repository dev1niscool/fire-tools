package org.firetools.adshelper;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private HelperSettings settings;
    private TextView status;
    private Button enableButton;
    private final SharedPreferences.OnSharedPreferenceChangeListener refreshListener =
            (preferences, key) -> refresh();

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        settings = new HelperSettings(this);
        AdsService.createChannel(this);

        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int inset = Math.round(24 * getResources().getDisplayMetrics().density);
        content.setPadding(inset, inset, inset, inset);
        scroll.addView(content, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(scroll);

        addText(content, "Experimental lock-screen ads helper", 24);
        addText(content, "Enable keeps one Android setting at 0 while the service runs. "
                + "Fire OS may still show ads. Stop pauses the service. "
                + "Restore stops the service and reapplies the original setting.", 16);
        status = addText(content, "", 16);

        enableButton = new Button(this);
        enableButton.setText("Enable");
        enableButton.setOnClickListener(view -> enable());
        content.addView(enableButton);

        Button stop = new Button(this);
        stop.setText("Stop");
        stop.setOnClickListener(view -> stop());
        content.addView(stop);

        Button restore = new Button(this);
        restore.setText("Restore");
        restore.setOnClickListener(view -> restore());
        content.addView(restore);
        refresh();
    }

    private TextView addText(LinearLayout content, String text, int size) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        layout.bottomMargin = Math.round(16 * getResources().getDisplayMetrics().density);
        content.addView(view, layout);
        return view;
    }

    @Override
    protected void onResume() {
        super.onResume();
        settings.preferences.registerOnSharedPreferenceChangeListener(refreshListener);
        refresh();
    }

    @Override
    protected void onPause() {
        settings.preferences.unregisterOnSharedPreferenceChangeListener(refreshListener);
        super.onPause();
    }

    private void refresh() {
        boolean enabled = settings.isEnabled();
        boolean active = enabled && AdsService.running;
        String state = active ? "Enabled • Service running"
                : enabled ? "Enabled • Service inactive" : "Disabled • Service inactive";
        String detail = settings.status();
        if (!settings.canWriteSettings()) {
            state += "\nADB permission is required to enable or restore.";
        }
        if (!detail.isEmpty()) {
            state += "\n" + detail;
        }
        status.setText(state);
        enableButton.setEnabled(!active);
    }

    private void enable() {
        if (!settings.canWriteSettings()) {
            settings.status("Grant WRITE_SECURE_SETTINGS through ADB and try again.");
            return;
        }
        try {
            settings.state().enable();
            AdsService.start(this);
            settings.status("Waiting for Android to start the service.");
        } catch (RuntimeException error) {
            String message = settings.errorMessage("Enable failed.", error);
            try {
                settings.state().stop();
            } catch (RuntimeException saveError) {
                message = settings.errorMessage(message, saveError);
            }
            settings.status(message);
        }
    }

    private void stop() {
        try {
            settings.state().stop();
            settings.status("Stopped. Use Restore to apply the saved setting.");
        } catch (RuntimeException error) {
            settings.status(settings.errorMessage("Could not save the stop request.", error));
        } finally {
            stopRunningService();
        }
    }

    private void restore() {
        try {
            if (settings.hasOriginal() && !settings.canWriteSettings()) {
                settings.state().stop();
                settings.status("Service stopped. Grant the ADB permission before restoring.");
                return;
            }
            boolean restored = settings.state().restore();
            settings.status(restored ? "Original Android setting restored."
                    : "Service stopped. There is no saved setting to restore.");
        } catch (RuntimeException error) {
            settings.status(settings.errorMessage("Restore could not complete.", error));
        } finally {
            stopRunningService();
        }
    }

    private void stopRunningService() {
        // A pending foreground start can now see the disabled flag and stop safely.
        if (AdsService.running) {
            stopService(new Intent(this, AdsService.class));
        }
    }
}
