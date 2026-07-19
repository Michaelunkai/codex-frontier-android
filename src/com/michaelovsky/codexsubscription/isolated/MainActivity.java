package com.michaelovsky.codexsubscription.isolated;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.MotionEvent;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.DownloadListener;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;

public final class MainActivity extends Activity {
    private static final String WEB_URL = RuntimeContract.WEB_URL;
    private static final int TERMUX_PERMISSION_REQUEST = 7;
    private static final int FILE_CHOOSER_REQUEST = 8;
    private static final int MEDIA_PERMISSION_REQUEST = 9;
    private static final long PAGE_LOAD_TIMEOUT_MS = 35_000L;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private FrameLayout rootContainer;
    private TextView loadingOverlay;
    private WebView webView;
    private ValueCallback<Uri[]> fileChooserCallback;
    private PermissionRequest pendingMediaPermission;
    private volatile boolean destroyed;
    private volatile boolean readinessWorkerRunning;
    private boolean guiLoaded;
    private boolean runtimePageLoading;
    private boolean recoveryScheduled;
    private boolean rendererRecoveryScheduled;
    private int pageLoadGeneration;
    private float refreshGestureStartY;
    private boolean refreshGestureEligible;

    @SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);

        rootContainer = new FrameLayout(this);
        rootContainer.setBackgroundColor(Color.rgb(5, 8, 23));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(5, 8, 23));
        webView.setAlpha(0f);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setFocusable(true);
        webView.setFocusableInTouchMode(true);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setTextZoom(100);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        if (android.os.Build.VERSION.SDK_INT >= 21) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        if (android.os.Build.VERSION.SDK_INT >= 26) {
            settings.setSafeBrowsingEnabled(true);
        }
        webView.setOnTouchListener(new View.OnTouchListener() {
            @Override public boolean onTouch(View view, MotionEvent event) {
                if (event == null) return false;
                if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    refreshGestureStartY = event.getY();
                    refreshGestureEligible = webView.getScrollY() <= 0;
                } else if (event.getActionMasked() == MotionEvent.ACTION_UP) {
                    float threshold = 110f * getResources().getDisplayMetrics().density;
                    if (refreshGestureEligible && event.getY() - refreshGestureStartY >= threshold) {
                        refreshGestureEligible = false;
                        refreshRuntimePage("pull-to-refresh");
                    }
                } else if (event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
                    refreshGestureEligible = false;
                }
                return false;
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return request != null && handleNavigation(request.getUrl());
            }

            @SuppressWarnings("deprecation")
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleNavigation(url == null ? null : Uri.parse(url));
            }

            @Override public void onPageStarted(WebView view, String url, Bitmap favicon) {
                if (url != null && url.startsWith(WEB_URL) && !runtimePageLoading) beginRuntimePageLoad();
            }

            @Override public void onPageFinished(WebView view, String url) {
                if (url != null && url.startsWith(WEB_URL)) revealWhenVisuallyReady(view);
            }

            @Override public void onPageCommitVisible(WebView view, String url) {
                if (url != null && url.startsWith(WEB_URL)) revealWhenVisuallyReady(view);
            }

            @Override public void onReceivedHttpError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceResponse response) {
                if (request != null && request.isForMainFrame()
                        && request.getUrl() != null
                        && request.getUrl().toString().startsWith(WEB_URL)
                        && response != null
                        && response.getStatusCode() >= 500) {
                    recoverRuntimePage("main-frame-http-" + response.getStatusCode());
                }
            }

            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (destroyed || rendererRecoveryScheduled) return true;
                rendererRecoveryScheduled = true;
                pageLoadGeneration += 1;
                guiLoaded = false;
                runtimePageLoading = false;
                recoveryScheduled = false;
                showStartingPage("Restoring the secure workspace…");
                startRuntimeWatchdog("renderer-process-gone");
                disposeWebView(view);
                mainHandler.postDelayed(new Runnable() {
                    @Override public void run() {
                        if (destroyed) return;
                        recreate();
                    }
                }, 500L);
                return true;
            }

            @Override public void onReceivedError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceError error) {
                if (request != null && request.isForMainFrame()
                        && request.getUrl() != null
                        && request.getUrl().toString().startsWith(WEB_URL)) {
                    recoverRuntimePage("main-frame-load-error");
                }
            }

            @SuppressWarnings("deprecation")
            @Override public void onReceivedError(
                    WebView view,
                    int errorCode,
                    String description,
                    String failingUrl) {
                if (failingUrl != null && failingUrl.startsWith(WEB_URL)) {
                    recoverRuntimePage("legacy-main-frame-load-error");
                }
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
                fileChooserCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER_REQUEST);
                    return true;
                } catch (RuntimeException error) {
                    fileChooserCallback = null;
                    return false;
                }
            }

            @Override public void onPermissionRequest(final PermissionRequest request) {
                mainHandler.post(new Runnable() {
                    @Override public void run() { requestMediaPermission(request); }
                });
            }
        });
        webView.setDownloadListener(new DownloadListener() {
            @Override public void onDownloadStart(
                    String url,
                    String userAgent,
                    String contentDisposition,
                    String mimeType,
                    long contentLength) {
                enqueueDownload(url, userAgent, contentDisposition, mimeType);
            }
        });

        loadingOverlay = new TextView(this);
        loadingOverlay.setBackgroundColor(Color.rgb(5, 8, 23));
        loadingOverlay.setTextColor(Color.rgb(238, 242, 255));
        loadingOverlay.setTextSize(19f);
        loadingOverlay.setGravity(Gravity.CENTER);
        loadingOverlay.setPadding(48, 48, 48, 48);
        loadingOverlay.setFocusable(true);
        loadingOverlay.setClickable(false);

        FrameLayout.LayoutParams fill = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT);
        rootContainer.addView(webView, fill);
        rootContainer.addView(loadingOverlay, fill);
        setContentView(rootContainer);
        showStartingPage("CODEX FRONTIER\n\nPreparing your private workspace…");
        ensureTermuxPermission();
        waitForRuntimeOnce();
    }

    private void showStartingPage(String message) {
        if (loadingOverlay == null) return;
        loadingOverlay.setText(message);
        loadingOverlay.setOnClickListener(null);
        loadingOverlay.setClickable(false);
        loadingOverlay.setVisibility(View.VISIBLE);
        loadingOverlay.bringToFront();
        if (!guiLoaded && webView != null) webView.setAlpha(0f);
    }

    private void ensureTermuxPermission() {
        if (checkSelfPermission("com.termux.permission.RUN_COMMAND") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"com.termux.permission.RUN_COMMAND"}, TERMUX_PERMISSION_REQUEST);
        } else {
            startRuntimeWatchdog("activity-created");
        }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == TERMUX_PERMISSION_REQUEST
                && results.length == 1
                && results[0] == PackageManager.PERMISSION_GRANTED) {
            startRuntimeWatchdog("termux-permission-granted");
            waitForRuntimeOnce();
        } else if (requestCode == MEDIA_PERMISSION_REQUEST && pendingMediaPermission != null) {
            grantApprovedMediaResources(pendingMediaPermission);
            pendingMediaPermission = null;
        }
    }

    private void requestMediaPermission(PermissionRequest request) {
        if (request == null || destroyed) return;
        ArrayList<String> needed = new ArrayList<String>();
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)
                    && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.RECORD_AUDIO);
            } else if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)
                    && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.CAMERA);
            }
        }
        if (!needed.isEmpty()) {
            pendingMediaPermission = request;
            requestPermissions(needed.toArray(new String[needed.size()]), MEDIA_PERMISSION_REQUEST);
        } else {
            grantApprovedMediaResources(request);
        }
    }

    private void grantApprovedMediaResources(PermissionRequest request) {
        ArrayList<String> approved = new ArrayList<String>();
        for (String resource : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)
                    && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                approved.add(resource);
            } else if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)
                    && checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                approved.add(resource);
            }
        }
        if (approved.isEmpty()) request.deny();
        else request.grant(approved.toArray(new String[approved.size()]));
    }

    private void startRuntimeWatchdog(String reason) {
        try {
            RuntimeContract.startWatchdog(this, reason);
        } catch (RuntimeException ignored) { }
    }

    private synchronized void waitForRuntimeOnce() {
        if (guiLoaded || runtimePageLoading || readinessWorkerRunning || destroyed) return;
        readinessWorkerRunning = true;
        new Thread(new Runnable() {
            @Override public void run() {
                boolean ready = false;
                for (int attempt = 0; attempt < 120 && !destroyed; attempt++) {
                    if (RuntimeContract.runtimeIsReady()) { ready = true; break; }
                    try { Thread.sleep(1000L); } catch (InterruptedException ignored) { break; }
                }
                final boolean finalReady = ready;
                readinessWorkerRunning = false;
                if (destroyed) return;
                mainHandler.post(new Runnable() {
                    @Override public void run() {
                        if (destroyed || guiLoaded) return;
                        if (finalReady) {
                            beginRuntimePageLoad();
                            webView.loadUrl(WEB_URL);
                        } else {
                            showStartupFailure();
                            mainHandler.postDelayed(new Runnable() {
                                @Override public void run() {
                                    if (destroyed || guiLoaded || runtimePageLoading) return;
                                    startRuntimeWatchdog("automatic-startup-retry");
                                    waitForRuntimeOnce();
                                }
                            }, 5000L);
                        }
                    }
                });
            }
        }, "codex-frontier-readiness").start();
    }

    private void recoverRuntimePage(String reason) {
        if (destroyed || rendererRecoveryScheduled || recoveryScheduled) return;
        recoveryScheduled = true;
        pageLoadGeneration += 1;
        guiLoaded = false;
        runtimePageLoading = false;
        if (webView != null) webView.stopLoading();
        showStartingPage("Reconnecting to your private workspace…");
        startRuntimeWatchdog(reason);
        final int recoveryGeneration = pageLoadGeneration;
        mainHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (destroyed || rendererRecoveryScheduled || recoveryGeneration != pageLoadGeneration) return;
                recoveryScheduled = false;
                if (guiLoaded || runtimePageLoading) return;
                waitForRuntimeOnce();
            }
        }, 1000L);
    }

    private void beginRuntimePageLoad() {
        runtimePageLoading = true;
        final int generation = ++pageLoadGeneration;
        mainHandler.postDelayed(new Runnable() {
            @Override public void run() {
                if (destroyed || generation != pageLoadGeneration || !runtimePageLoading) return;
                webView.stopLoading();
                recoverRuntimePage("page-load-timeout");
            }
        }, PAGE_LOAD_TIMEOUT_MS);
    }

    private void refreshRuntimePage(final String reason) {
        if (destroyed || rendererRecoveryScheduled) return;
        startRuntimeWatchdog(reason);
        new Thread(new Runnable() {
            @Override public void run() {
                final boolean ready = RuntimeContract.runtimeIsReady();
                mainHandler.post(new Runnable() {
                    @Override public void run() {
                        if (destroyed) return;
                        if (!ready) {
                            recoverRuntimePage(reason + "-runtime-unavailable");
                            return;
                        }
                        pageLoadGeneration += 1;
                        runtimePageLoading = false;
                        webView.stopLoading();
                        String currentUrl = webView.getUrl();
                        if (guiLoaded && currentUrl != null && currentUrl.startsWith(WEB_URL)) {
                            webView.evaluateJavascript(
                                    "window.dispatchEvent(new CustomEvent('codex-frontier-soft-refresh'))",
                                    null);
                        } else {
                            beginRuntimePageLoad();
                            webView.loadUrl(WEB_URL);
                        }
                    }
                });
            }
        }, "codex-frontier-manual-refresh").start();
    }

    private void showStartupFailure() {
        showStartingPage("Codex Frontier is still preparing the workspace.\n\nTap once to retry now. Automatic recovery remains active.");
        loadingOverlay.setClickable(true);
        loadingOverlay.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                if (destroyed || readinessWorkerRunning) return;
                showStartingPage("Retrying the private workspace…");
                startRuntimeWatchdog("manual-retry");
                waitForRuntimeOnce();
            }
        });
    }

    private boolean handleNavigation(Uri uri) {
        if (uri == null) return false;
        String url = uri.toString();
        if (url.startsWith(WEB_URL) || "about:blank".equals(url) || url.startsWith("data:")) return false;
        if ("codex-frontier".equals(uri.getScheme()) && "retry".equals(uri.getHost())) {
            guiLoaded = false;
            runtimePageLoading = false;
            showStartingPage("Retrying the private workspace…");
            startRuntimeWatchdog("manual-retry");
            waitForRuntimeOnce();
            return true;
        }
        if ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (RuntimeException ignored) { }
            return true;
        }
        return false;
    }

    private void enqueueDownload(String url, String userAgent, String contentDisposition, String mimeType) {
        if (url == null || !(url.startsWith(WEB_URL) || url.startsWith("https://"))) {
            Toast.makeText(this, "Unsupported download source", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            String fileName = URLUtil.guessFileName(url, contentDisposition, mimeType);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setTitle(fileName);
            request.setDescription("Downloaded by Codex Frontier");
            request.setMimeType(mimeType);
            if (userAgent != null && !userAgent.isEmpty()) request.addRequestHeader("User-Agent", userAgent);
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            if (android.os.Build.VERSION.SDK_INT >= 29) {
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
            } else {
                request.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, fileName);
            }
            DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            if (manager == null) throw new IllegalStateException("Download manager unavailable");
            manager.enqueue(request);
            Toast.makeText(this, "Download started", Toast.LENGTH_SHORT).show();
        } catch (RuntimeException error) {
            Toast.makeText(this, "Download could not start", Toast.LENGTH_SHORT).show();
        }
    }

    @Override protected void onResume() {
        super.onResume();
        if (!destroyed
                && checkSelfPermission("com.termux.permission.RUN_COMMAND") == PackageManager.PERMISSION_GRANTED) {
            startRuntimeWatchdog("activity-resumed");
            if (!guiLoaded && !runtimePageLoading) waitForRuntimeOnce();
            else if (guiLoaded) verifyRuntimeAfterResume();
        }
    }

    private void verifyRuntimeAfterResume() {
        new Thread(new Runnable() {
            @Override public void run() {
                if (destroyed || RuntimeContract.runtimeIsReady()) return;
                mainHandler.post(new Runnable() {
                    @Override public void run() { recoverRuntimePage("resume-health-failed"); }
                });
            }
        }, "codex-frontier-resume-health").start();
    }

    private void revealWhenVisuallyReady(final WebView view) {
        if (destroyed || view == null || view != webView) return;
        final int generation = pageLoadGeneration;
        view.postVisualStateCallback(generation, new WebView.VisualStateCallback() {
            @Override public void onComplete(long requestId) {
                if (destroyed || view != webView || generation != pageLoadGeneration) return;
                recoveryScheduled = false;
                guiLoaded = true;
                runtimePageLoading = false;
                pageLoadGeneration += 1;
                view.setAlpha(1f);
                view.requestFocus(View.FOCUS_DOWN);
                if (loadingOverlay != null) loadingOverlay.setVisibility(View.GONE);
            }
        });
    }

    private void disposeWebView(WebView view) {
        if (view == null) return;
        try {
            view.stopLoading();
            view.setWebChromeClient(null);
            view.setWebViewClient(null);
            if (rootContainer != null) rootContainer.removeView(view);
            view.destroy();
        } catch (RuntimeException ignored) { }
        if (view == webView) webView = null;
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST && fileChooserCallback != null) {
            Uri[] result = resultCode == RESULT_OK ? WebChromeClient.FileChooserParams.parseResult(resultCode, data) : null;
            fileChooserCallback.onReceiveValue(result);
            fileChooserCallback = null;
        }
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        pageLoadGeneration += 1;
        mainHandler.removeCallbacksAndMessages(null);
        if (fileChooserCallback != null) fileChooserCallback.onReceiveValue(null);
        if (pendingMediaPermission != null) pendingMediaPermission.deny();
        disposeWebView(webView);
        super.onDestroy();
    }
}
