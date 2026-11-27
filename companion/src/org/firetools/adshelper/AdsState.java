package org.firetools.adshelper;

import java.util.Objects;

final class AdsState {
    interface Storage {
        boolean isEnabled();
        void setEnabled(boolean enabled);
        boolean hasOriginal();
        Entry originalValue();
        void saveOriginal(Entry entry);
        void clearOriginal();
    }

    interface Setting {
        String read();
        Entry snapshot();
        boolean write(String value);
        void delete();
    }

    static final class Entry {
        final boolean present;
        final String value;

        Entry(boolean present, String value) {
            this.present = present;
            this.value = value;
        }

        boolean matches(Entry other) {
            return present == other.present && Objects.equals(value, other.value);
        }
    }

    private final Storage storage;
    private final Setting setting;

    AdsState(Storage storage, Setting setting) {
        this.storage = storage;
        this.setting = setting;
    }

    void enable() {
        storage.setEnabled(true);
    }

    void stop() {
        storage.setEnabled(false);
    }

    void apply() {
        if (!storage.isEnabled()) {
            return;
        }
        String current;
        if (storage.hasOriginal()) {
            current = setting.read();
        } else {
            Entry original = setting.snapshot();
            storage.saveOriginal(original);
            current = original.value;
        }
        if (!"0".equals(current) && (!setting.write("0") || !"0".equals(setting.read()))) {
            throw new IllegalStateException("Android did not retain the requested setting value.");
        }
    }

    boolean restore() {
        stop();
        if (!storage.hasOriginal()) {
            return false;
        }
        Entry original = storage.originalValue();
        if (!original.matches(setting.snapshot())) {
            if (!original.present) {
                setting.delete();
            } else if (!setting.write(original.value)) {
                throw new IllegalStateException("Android refused to write the original setting.");
            }
            if (!original.matches(setting.snapshot())) {
                throw new IllegalStateException("Android did not restore the original setting.");
            }
        }
        storage.clearOriginal();
        return true;
    }
}
