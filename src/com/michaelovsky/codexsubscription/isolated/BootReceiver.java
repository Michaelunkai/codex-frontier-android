package com.michaelovsky.codexsubscription.isolated;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public final class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "CodexFrontierBoot";

    @Override public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "unknown" : intent.getAction();
        if (Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)) return;
        try {
            RuntimeContract.startWatchdog(context, action);
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to start runtime watchdog after " + action, error);
        }
    }
}
