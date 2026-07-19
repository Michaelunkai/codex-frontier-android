package com.michaelovsky.codexsubscription.isolated;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;

public final class RuntimeCommandResultReceiver extends BroadcastReceiver {
    private static final String TAG = "CodexFrontierResult";

    @Override public void onReceive(Context context, Intent intent) {
        Bundle result = intent == null ? null : intent.getBundleExtra("result");
        int exitCode = result == null ? Integer.MIN_VALUE : result.getInt("exitCode", Integer.MIN_VALUE);
        int internalError = result == null ? Integer.MIN_VALUE : result.getInt("err", Integer.MIN_VALUE);
        String errorMessage = result == null ? "missing result bundle" : result.getString("errmsg", "");

        SharedPreferences preferences = context.getSharedPreferences("runtime_watchdog", Context.MODE_PRIVATE);
        preferences.edit()
                .putLong("lastCommandResultAt", System.currentTimeMillis())
                .putInt("lastCommandExitCode", exitCode)
                .putInt("lastCommandInternalError", internalError)
                .putString("lastCommandError", errorMessage)
                .apply();

        Log.i(TAG, "Termux command result exit=" + exitCode + " internalError=" + internalError);
        Intent check = new Intent(context, RuntimeWatchdogService.class);
        check.setAction(RuntimeContract.ACTION_CHECK_NOW);
        try {
            context.startService(check);
        } catch (RuntimeException error) {
            Log.w(TAG, "Unable to request immediate runtime health check", error);
        }
    }
}
