package com.dinglong.mahjong;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.atomic.AtomicBoolean;

@CapacitorPlugin(name = "ApkUpdater")
public class ApkUpdaterPlugin extends Plugin {
    private final AtomicBoolean downloading = new AtomicBoolean(false);
    private static final String PREFS = "apk_updater";

    private File updateDirectory() throws Exception {
        File cache = getContext().getExternalCacheDir();
        if (cache == null) throw new Exception("External cache unavailable");
        File directory = new File(cache, "updates");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new Exception("Cannot create update directory");
        return directory.getCanonicalFile();
    }

    @PluginMethod
    public void download(PluginCall call) {
        String url = call.getString("url");
        if (url == null || !url.startsWith("https://")) { call.reject("HTTPS APK URL required"); return; }
        if (!downloading.compareAndSet(false, true)) { call.reject("Download already running"); return; }
        new Thread(() -> {
            HttpURLConnection connection = null;
            File partial = null;
            try {
                File directory = updateDirectory();
                partial = new File(directory, "update.apk.part");
                connection = (HttpURLConnection) new URL(url).openConnection();
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(30000);
                connection.setInstanceFollowRedirects(true);
                int status = connection.getResponseCode();
                if (status != 200 || !"https".equals(connection.getURL().getProtocol())) throw new Exception("APK download HTTP " + status);
                long total = connection.getContentLengthLong(), received = 0, lastEvent = 0;
                try (InputStream input = connection.getInputStream(); FileOutputStream output = new FileOutputStream(partial)) {
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        output.write(buffer, 0, count);
                        received += count;
                        long now = android.os.SystemClock.elapsedRealtime();
                        if (now - lastEvent >= 250) { emitProgress(received, total); lastEvent = now; }
                    }
                }
                if (received == 0 || (total > 0 && received != total)) throw new Exception("Incomplete APK download");
                File apk = new File(directory, "update.apk");
                if (apk.exists() && !apk.delete()) throw new Exception("Cannot replace APK");
                if (!partial.renameTo(apk)) throw new Exception("Cannot save APK");
                emitProgress(received, received);
                JSObject result = new JSObject();
                result.put("path", apk.getCanonicalPath());
                call.resolve(result);
            } catch (Exception error) {
                if (partial != null) partial.delete();
                call.reject("APK download failed", error);
            } finally {
                if (connection != null) connection.disconnect();
                downloading.set(false);
            }
        }, "apk-download").start();
    }

    private void emitProgress(long received, long total) {
        JSObject event = new JSObject();
        event.put("received", received);
        event.put("total", total);
        event.put("progress", total > 0 ? (int) Math.min(100, received * 100 / total) : JSObject.NULL);
        notifyListeners("downloadProgress", event);
    }

    private File checkedApk(String path) throws Exception {
        if (path == null) throw new Exception("APK path required");
        File apk = new File(path).getCanonicalFile();
        if (!updateDirectory().equals(apk.getParentFile()) || !apk.getName().equals("update.apk") || !apk.isFile()) {
            throw new Exception("Invalid APK path");
        }
        return apk;
    }

    private boolean canInstall() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getContext().getPackageManager().canRequestPackageInstalls();
    }

    private void openInstaller(File apk) {
        Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        getActivity().startActivity(intent);
    }

    @PluginMethod
    public void install(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                File apk = checkedApk(call.getString("path"));
                boolean permissionRequired = !canInstall();
                if (permissionRequired) {
                    getContext().getSharedPreferences(PREFS, 0).edit().putString("pending", apk.getPath()).apply();
                    Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getContext().getPackageName()));
                    getActivity().startActivity(intent);
                } else { openInstaller(apk); }
                JSObject result = new JSObject();
                result.put("permissionRequired", permissionRequired);
                call.resolve(result);
            } catch (Exception error) { call.reject("Cannot open APK installer", error); }
        });
    }

    @Override
    protected void handleOnResume() {
        String path = getContext().getSharedPreferences(PREFS, 0).getString("pending", null);
        if (path == null || !canInstall()) return;
        getContext().getSharedPreferences(PREFS, 0).edit().remove("pending").apply();
        try { openInstaller(checkedApk(path)); }
        catch (Exception error) {
            JSObject event = new JSObject();
            event.put("message", error.getMessage());
            notifyListeners("installError", event);
        }
    }
}
