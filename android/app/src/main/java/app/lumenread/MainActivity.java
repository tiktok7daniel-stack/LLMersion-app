package app.lumenread;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * LumenRead for Android: a native shell around the LumenRead web interface.
 *
 * The models (translation, voice, tutor, OCR) run on the learner's own computer; this app
 * shows the interface served by that machine. The interface is bilingual and switches to
 * right-to-left by itself, so the shell only has to host it: it asks for the microphone,
 * opens the system file picker for PDF import, keeps the screen text selectable for word
 * taps, and remembers the server address.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "lumenread";
    private static final String KEY_URL = "server_url";
    private static final int REQ_MIC = 7;
    private static final int REQ_FILE = 8;

    private WebView web;
    private ValueCallback<Uri[]> filePathCallback;
    private PermissionRequest pendingPermission;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String url = prefs.getString(KEY_URL, "");
        if (url.isEmpty()) {
            showConnectScreen();
        } else {
            showWeb(url);
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    // ------------------------------------------------------------------ connect screen
    private void showConnectScreen() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(48), dp(24), dp(24));
        box.setGravity(Gravity.CENTER_HORIZONTAL);

        TextView name = new TextView(this);
        name.setText(R.string.app_name);
        name.setTextSize(30);
        name.setTextColor(Color.parseColor("#1D4ED8"));
        name.setTextDirection(View.TEXT_DIRECTION_LTR);
        name.setGravity(Gravity.CENTER);
        box.addView(name);

        TextView tag = new TextView(this);
        tag.setText(R.string.tagline);
        tag.setTextSize(15);
        tag.setTextColor(Color.parseColor("#475569"));
        tag.setGravity(Gravity.CENTER);
        box.addView(tag);

        TextView title = new TextView(this);
        title.setText(R.string.connect_title);
        title.setTextSize(18);
        title.setTextColor(Color.parseColor("#0F172A"));
        title.setPadding(0, dp(32), 0, dp(8));
        box.addView(title);

        TextView body = new TextView(this);
        body.setText(R.string.connect_body);
        body.setTextSize(14);
        body.setTextColor(Color.parseColor("#475569"));
        body.setPadding(0, 0, 0, dp(16));
        box.addView(body);

        final EditText urlField = new EditText(this);
        urlField.setHint(R.string.server_hint);
        urlField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        urlField.setTextDirection(View.TEXT_DIRECTION_LTR);
        urlField.setSingleLine(true);
        urlField.setText(prefs.getString(KEY_URL, ""));
        box.addView(urlField, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        final EditText tokenField = new EditText(this);
        tokenField.setHint(R.string.token_hint);
        tokenField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        tokenField.setTextDirection(View.TEXT_DIRECTION_LTR);
        tokenField.setSingleLine(true);
        box.addView(tokenField, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        final TextView error = new TextView(this);
        error.setTextColor(Color.parseColor("#B91C1C"));
        error.setPadding(0, dp(8), 0, 0);
        box.addView(error);

        Button go = new Button(this);
        go.setText(R.string.connect);
        go.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String url = normalise(urlField.getText().toString());
                if (url == null) {
                    error.setText(R.string.bad_url);
                    return;
                }
                String token = tokenField.getText().toString().trim();
                if (!token.isEmpty()) {
                    url = url + (url.contains("?") ? "&" : "/?") + "token=" + Uri.encode(token);
                }
                prefs.edit().putString(KEY_URL, url).apply();
                showWeb(url);
            }
        });
        box.addView(go, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#F8FAFC"));
        scroll.addView(box);
        setContentView(scroll);
    }

    /** "192.168.1.20:8848" -> "http://192.168.1.20:8848"; null if it cannot be a server address. */
    static String normalise(String raw) {
        String s = raw == null ? "" : raw.trim();
        if (s.isEmpty() || s.contains(" ")) return null;
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://" + s;
        Uri u = Uri.parse(s);
        if (u.getHost() == null || u.getHost().isEmpty()) return null;
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }

    // ------------------------------------------------------------------ web view
    private void showWeb(final String url) {
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);                    // saved language, theme, onboarding
        s.setMediaPlaybackRequiresUserGesture(false);    // read-along starts from the play button
        s.setAllowFileAccess(false);
        s.setSupportZoom(false);
        CookieManager.getInstance().setAcceptCookie(true);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                Uri home = Uri.parse(url);
                if (home.getHost() != null && home.getHost().equals(u.getHost())) return false;
                // links to other sites (About: upstream repo, paper) open in the browser
                startActivity(new Intent(Intent.ACTION_VIEW, u));
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showLoadError();
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                // speaking practice and pronunciation scoring need the microphone
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(request.getResources());
                } else {
                    pendingPermission = request;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                // PDF / text import
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILE);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }
        });

        web.loadUrl(url);
    }

    private void showLoadError() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(24), dp(24), dp(24), dp(24));
        TextView msg = new TextView(this);
        msg.setText(R.string.load_failed);
        msg.setTextSize(16);
        msg.setGravity(Gravity.CENTER);
        box.addView(msg);
        Button retry = new Button(this);
        retry.setText(R.string.retry);
        retry.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showWeb(prefs.getString(KEY_URL, "")); }
        });
        box.addView(retry);
        Button change = new Button(this);
        change.setText(R.string.change_server);
        change.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showConnectScreen(); }
        });
        box.addView(change);
        setContentView(box);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        super.onRequestPermissionsResult(code, perms, results);
        if (code == REQ_MIC && pendingPermission != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermission.grant(pendingPermission.getResources());
            } else {
                pendingPermission.deny();
            }
            pendingPermission = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code == REQ_FILE && filePathCallback != null) {
            filePathCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            filePathCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
