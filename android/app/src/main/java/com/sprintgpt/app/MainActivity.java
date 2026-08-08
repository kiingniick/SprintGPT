package com.sprintgpt.app;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.ValueCallback;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends Activity {

    private static final String URL = "http://127.0.0.1:5000/";
    private static final int FILE_CHOOSER = 42;

    private WebView web;
    private boolean serverUp = false;
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
        "<p>Warming up your coach&hellip;</p><div class='s'></div></body></html>";

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

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                if (url != null && url.startsWith("http")) {
                    serverUp = true;
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    showLoading();
                    handler.postDelayed(retry, 1200);
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
        showLoading();

        // Boot the embedded Python + Flask server on a background thread.
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

        // Give the server a head start, then begin trying to load it.
        handler.postDelayed(retry, 2500);
    }

    private final Runnable retry = new Runnable() {
        @Override
        public void run() {
            if (serverUp) {
                return;
            }
            web.loadUrl(URL);
            handler.postDelayed(this, 1500);
        }
    };

    private void showLoading() {
        web.loadDataWithBaseURL(null, LOADING_HTML, "text/html", "utf-8", null);
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
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
