package com.sprintgpt.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.ValueCallback;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Hosts SprintGPT in a WebView. Two ways to run:
 *
 *  - On-device (default, fully offline): boot the embedded Python/Flask server
 *    and load it from http://127.0.0.1:5000/.
 *  - Remote server: point the app at a SprintGPT you host yourself, so it works
 *    over mobile data and your account/data sync with the website.
 *
 * The choice is stored in SharedPreferences and can be changed anytime from the
 * in-app "App connection" link (which navigates to sprintgpt://settings) or the
 * connection error screen.
 */
public class MainActivity extends Activity {

    private static final String LOCAL_URL = "http://127.0.0.1:5000/";
    private static final String SETTINGS_SCHEME = "sprintgpt://settings";
    private static final int FILE_CHOOSER = 42;

    private static final String PREFS = "sprintgpt";
    private static final String KEY_MODE = "mode";       // "device" | "server"
    private static final String KEY_URL = "server_url";
    private static final String KEY_SKIP_VERSION = "skip_version";  // update the user dismissed
    private static final String MODE_DEVICE = "device";
    private static final String MODE_SERVER = "server";

    // Public, always-online manifest of the newest release (served from GitHub
    // Pages, so update checks work even when the tunnel/server is down or the app
    // is running fully on-device).
    private static final String UPDATE_URL =
        "https://kiingniick.github.io/SprintGPT/app-version.json";

    private WebView web;
    private boolean serverStarted = false;   // embedded Python launched
    private boolean loaded = false;          // a real http page is showing
    private boolean nativeScreen = false;    // setup/error page is showing
    private String target = LOCAL_URL;       // current http target to load
    private boolean deviceMode = true;

    private ValueCallback<Uri[]> filePathCallback;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private static final String LOADING_HTML =
        "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>" +
        "<style>html,body{height:100%;margin:0}body{background:#0b0f17;color:#e7ecf5;" +
        "font-family:-apple-system,Segoe UI,Roboto,sans-serif;display:flex;align-items:center;" +
        "justify-content:center;flex-direction:column}" +
        ".mark{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#34d399,#22d3ee);" +
        "display:flex;align-items:center;justify-content:center;font-weight:800;font-size:34px;color:#04231b;margin-bottom:18px}" +
        ".s{width:34px;height:34px;border:3px solid #26314a;border-top-color:#34d399;border-radius:50%;" +
        "animation:spin .8s linear infinite;margin-top:22px}" +
        "@keyframes spin{to{transform:rotate(360deg)}}h1{font-size:20px;margin:0}p{color:#93a0b8;margin:8px 0 0}" +
        "</style></head><body><div class='mark'>S</div><h1>Starting SprintGPT</h1>" +
        "<p id='msg'>Warming up your coach&hellip;</p><div class='s'></div></body></html>";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0b0f17"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        // Tag the User-Agent so the web app knows it's running inside the app and
        // can show the "App connection" link.
        s.setUserAgentString(s.getUserAgentString() + " SprintGPTApp/1.0");

        web.addJavascriptInterface(new Bridge(), "SprintGPTNative");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(request.getUrl() != null ? request.getUrl().toString() : null);
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (url != null && url.startsWith("http")) {
                    loaded = true;
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request == null || !request.isForMainFrame()) {
                    return;
                }
                if (deviceMode) {
                    // Embedded server may still be warming up: keep retrying.
                    if (!loaded) {
                        showLoading();
                        handler.postDelayed(retry, 1200);
                    }
                } else {
                    showServerError();
                }
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                filePathCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        setContentView(web);

        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String mode = prefs.getString(KEY_MODE, null);
        if (mode == null) {
            showSetup();            // first launch: let the user choose.
        } else {
            applyMode();
        }

        // Give the app a few seconds to settle, then quietly check for a newer build.
        handler.postDelayed(new Runnable() {
            @Override public void run() { checkForUpdate(); }
        }, 4000);
    }

    // ---- self-update reminder ----------------------------------------------

    /** Fetch the published version manifest off the UI thread and, if a newer
     *  build exists, remind the user with a dismissible dialog. Fails silently
     *  (no network, offline, etc.) — an update check should never interrupt use. */
    private void checkForUpdate() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection c = null;
                try {
                    c = (HttpURLConnection) new URL(UPDATE_URL).openConnection();
                    c.setConnectTimeout(6000);
                    c.setReadTimeout(6000);
                    c.setRequestProperty("Cache-Control", "no-cache");
                    if (c.getResponseCode() != 200) {
                        return;
                    }
                    BufferedReader r = new BufferedReader(
                        new InputStreamReader(c.getInputStream(), "UTF-8"));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) {
                        sb.append(line);
                    }
                    r.close();

                    JSONObject o = new JSONObject(sb.toString());
                    final int latest = o.optInt("versionCode", 0);
                    final String name = o.optString("versionName", "");
                    final String apk = o.optString("apkUrl", o.optString("url", ""));
                    final String notes = o.optString("notes", "");

                    if (latest > BuildConfig.VERSION_CODE && apk != null && !apk.isEmpty()) {
                        handler.post(new Runnable() {
                            @Override public void run() {
                                promptUpdate(latest, name, apk, notes);
                            }
                        });
                    }
                } catch (Throwable ignored) {
                    // Offline or unreachable: skip silently, try again next launch.
                } finally {
                    if (c != null) {
                        c.disconnect();
                    }
                }
            }
        }, "sprintgpt-update-check").start();
    }

    private void promptUpdate(final int latest, String name, final String apkUrl, String notes) {
        if (isFinishing()) {
            return;
        }
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        // Respect "Skip this version": don't nag again until an even newer build.
        if (prefs.getInt(KEY_SKIP_VERSION, 0) >= latest) {
            return;
        }
        String msg = "A new version" + (name == null || name.isEmpty() ? "" : " (" + name + ")")
                + " of SprintGPT is available.";
        if (notes != null && !notes.isEmpty()) {
            msg += "\n\n" + notes;
        }
        new AlertDialog.Builder(this)
            .setTitle("Update available")
            .setMessage(msg)
            .setCancelable(true)
            .setPositiveButton("Update now", new DialogInterface.OnClickListener() {
                @Override public void onClick(DialogInterface d, int which) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(apkUrl)));
                    } catch (Throwable ignored) {}
                }
            })
            .setNegativeButton("Later", null)
            .setNeutralButton("Skip this version", new DialogInterface.OnClickListener() {
                @Override public void onClick(DialogInterface d, int which) {
                    getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putInt(KEY_SKIP_VERSION, latest).apply();
                }
            })
            .show();
    }

    /** Intercept our custom scheme so any in-app link can open the setup screen. */
    private boolean handleUrl(String url) {
        if (url != null && url.startsWith(SETTINGS_SCHEME)) {
            showSetup();
            return true;
        }
        return false;
    }

    /** Read the saved mode and start the right thing. */
    private void applyMode() {
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String mode = prefs.getString(KEY_MODE, MODE_DEVICE);
        loaded = false;
        nativeScreen = false;
        if (MODE_SERVER.equals(mode)) {
            deviceMode = false;
            target = prefs.getString(KEY_URL, "");
            if (target == null || target.isEmpty()) {
                showSetup();
                return;
            }
            showLoading();
            web.loadUrl(target);
        } else {
            deviceMode = true;
            target = LOCAL_URL;
            boolean wasStarted = serverStarted;
            startServerIfNeeded();
            showLoading();
            // Cold boot: give the embedded server a head start. Already running
            // (e.g. switching back from server mode): retry almost immediately.
            handler.postDelayed(retry, wasStarted ? 300 : 2500);
        }
    }

    private void startServerIfNeeded() {
        if (serverStarted) {
            return;
        }
        serverStarted = true;
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        final String filesDir = getFilesDir().getAbsolutePath();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    Python.getInstance().getModule("android_main").callAttr("main", filesDir);
                } catch (Throwable t) {
                    t.printStackTrace();
                }
            }
        }, "sprintgpt-server").start();
    }

    private final Runnable retry = new Runnable() {
        @Override
        public void run() {
            if (loaded || !deviceMode) {
                return;
            }
            web.loadUrl(LOCAL_URL);
            handler.postDelayed(this, 1500);
        }
    };

    private void showLoading() {
        nativeScreen = false;
        web.loadDataWithBaseURL(null, LOADING_HTML, "text/html", "utf-8", null);
    }

    // ---- native setup / error screens (talk back via SprintGPTNative) -------

    private void showSetup() {
        nativeScreen = true;
        handler.removeCallbacks(retry);
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String savedUrl = prefs.getString(KEY_URL, "");
        if (savedUrl == null || savedUrl.isEmpty()) {
            savedUrl = BuildConfig.DEFAULT_SERVER_URL;   // pre-fill the recommended host
        }
        String html = buildSetupHtml(savedUrl == null ? "" : savedUrl, null);
        web.loadDataWithBaseURL("https://sprintgpt.local/", html, "text/html", "utf-8", null);
    }

    private void showServerError() {
        nativeScreen = true;
        handler.removeCallbacks(retry);
        SharedPreferences prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String savedUrl = prefs.getString(KEY_URL, "");
        String html = buildSetupHtml(savedUrl == null ? "" : savedUrl,
            "Couldn't reach that server. Check the address and your connection, or switch to running on this phone.");
        web.loadDataWithBaseURL("https://sprintgpt.local/", html, "text/html", "utf-8", null);
    }

    private String buildSetupHtml(String savedUrl, String error) {
        String errBlock = "";
        if (error != null) {
            errBlock = "<div class='err'>" + escape(error) + "</div>";
        }
        String recommended = BuildConfig.DEFAULT_SERVER_URL;
        String recoBlock = "";
        if (recommended != null && !recommended.isEmpty()) {
            recoBlock =
                "<button class='ghost' style='margin-bottom:12px' " +
                "onclick=\"SprintGPTNative.chooseServer('" + escape(recommended) + "')\">" +
                "Use recommended server</button>";
        }
        return "<!doctype html><html><head>" +
            "<meta name='viewport' content='width=device-width,initial-scale=1'>" +
            "<style>" +
            "*{box-sizing:border-box}html,body{margin:0;min-height:100%}" +
            "body{background:#0b0f17;color:#e7ecf5;font-family:-apple-system,Segoe UI,Roboto,sans-serif;" +
            "padding:28px 22px 40px;line-height:1.5}" +
            ".mark{width:56px;height:56px;border-radius:16px;background:linear-gradient(135deg,#34d399,#22d3ee);" +
            "display:flex;align-items:center;justify-content:center;font-weight:800;font-size:30px;color:#04231b;margin-bottom:16px}" +
            "h1{font-size:22px;margin:0 0 4px}.sub{color:#93a0b8;margin:0 0 22px}" +
            ".err{background:#3a1720;border:1px solid #7f1d1d;color:#fecaca;padding:12px 14px;border-radius:12px;margin-bottom:20px;font-size:14px}" +
            ".card{background:#131a27;border:1px solid #26314a;border-radius:16px;padding:18px;margin-bottom:16px}" +
            ".card h2{font-size:16px;margin:0 0 6px}.card p{color:#93a0b8;font-size:14px;margin:0 0 14px}" +
            "input{width:100%;padding:13px 14px;border-radius:12px;border:1px solid #2b3650;background:#0b0f17;" +
            "color:#e7ecf5;font-size:15px;margin-bottom:12px}" +
            "button{width:100%;padding:14px;border:0;border-radius:12px;font-size:15px;font-weight:700;cursor:pointer}" +
            ".primary{background:linear-gradient(135deg,#34d399,#22d3ee);color:#04231b}" +
            ".ghost{background:#1b2436;color:#e7ecf5;border:1px solid #2b3650}" +
            ".hint{color:#6b7688;font-size:12px;margin-top:16px;text-align:center}" +
            "</style></head><body>" +
            "<div class='mark'>S</div>" +
            "<h1>Choose how to run</h1>" +
            "<p class='sub'>You can switch anytime from the app menu.</p>" +
            errBlock +
            "<div class='card'>" +
            "<h2>Run on this phone</h2>" +
            "<p>Everything stays on your device and works fully offline. Best if you don't need to share data with the website.</p>" +
            "<button class='primary' onclick=\"SprintGPTNative.chooseDevice()\">Run on this phone</button>" +
            "</div>" +
            "<div class='card'>" +
            "<h2>Connect to a server</h2>" +
            "<p>Point the app at a SprintGPT you host yourself. Works over mobile data and keeps the app and website in sync.</p>" +
            recoBlock +
            "<input id='url' type='url' inputmode='url' autocapitalize='none' autocorrect='off' spellcheck='false' " +
            "placeholder='https://your-sprintgpt.example.com' value='" + escape(savedUrl) + "'>" +
            "<button class='primary' onclick=\"SprintGPTNative.chooseServer(document.getElementById('url').value)\">Connect</button>" +
            "</div>" +
            "<div class='hint'>Tip: on the website, log in the same way to see the same runs.</div>" +
            "</body></html>";
    }

    private static String escape(String v) {
        if (v == null) return "";
        return v.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;");
    }

    /** JS -> native bridge used only by the setup/error screens. */
    private class Bridge {
        @JavascriptInterface
        public void chooseDevice() {
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_MODE, MODE_DEVICE).apply();
            handler.post(new Runnable() {
                @Override public void run() { applyMode(); }
            });
        }

        @JavascriptInterface
        public void chooseServer(String rawUrl) {
            final String url = normalizeUrl(rawUrl);
            if (url == null) {
                handler.post(new Runnable() {
                    @Override public void run() {
                        SharedPreferences p = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
                        web.loadDataWithBaseURL("https://sprintgpt.local/",
                            buildSetupHtml(p.getString(KEY_URL, ""),
                                "Please enter a full address, like https://your-sprintgpt.example.com"),
                            "text/html", "utf-8", null);
                    }
                });
                return;
            }
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_MODE, MODE_SERVER)
                .putString(KEY_URL, url)
                .apply();
            handler.post(new Runnable() {
                @Override public void run() { applyMode(); }
            });
        }
    }

    /** Normalize user input into a usable http(s) URL, or null if unusable. */
    private static String normalizeUrl(String raw) {
        if (raw == null) {
            return null;
        }
        String url = raw.trim();
        if (url.isEmpty()) {
            return null;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://" + url;
        }
        // Drop a trailing slash so we don't build "//" paths later.
        while (url.endsWith("/")) {
            url = url.substring(0, url.length() - 1);
        }
        if (url.length() <= "https://".length()) {
            return null;
        }
        return url + "/";
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER) {
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                results = new Uri[]{ data.getData() };
            }
            if (filePathCallback != null) {
                filePathCallback.onReceiveValue(results);
                filePathCallback = null;
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }

    @Override
    public void onBackPressed() {
        if (!nativeScreen && web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
