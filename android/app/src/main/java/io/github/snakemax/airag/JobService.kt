package io.github.snakemax.airag

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.chaquo.python.Python

/**
 * Keeps AIRAG's process alive while searches or explainers run, so they finish even when the app
 * is closed or swiped away. Shows a persistent notification with what's running and a Cancel button.
 * Started and stopped by Python (airag/android_bridge.py) through Bridge.jobsChanged().
 */
class JobService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CANCEL -> {
                try { Python.getInstance().getModule("airag.android_bridge").callAttr("cancel_all") } catch (_: Throwable) { }
                return START_NOT_STICKY
            }
            ACTION_STOP -> { stop(); return START_NOT_STICKY }
        }
        val n = progress(this, intent?.getStringExtra(EXTRA_TITLE) ?: "", intent?.getIntExtra(EXTRA_COUNT, 1) ?: 1,
            intent?.getStringExtra(EXTRA_LINES) ?: "")
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0
        ServiceCompat.startForeground(this, ID_PROGRESS, n, type)
        running = true
        holdWakeLock()
        return START_NOT_STICKY
    }

    @SuppressLint("WakelockTimeout")
    private fun holdWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        // keeps the CPU awake while the screen is off; released when the last job ends (or after 2 h at most)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AIRAG:jobs").apply { acquire(2 * 60 * 60 * 1000L) }
    }

    private fun stop() {
        running = false
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        running = false
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    companion object {
        // v2: default importance so the icon shows in the status bar (a channel's importance can't change later)
        const val CHANNEL_PROGRESS = "jobs_v2"
        const val CHANNEL_DONE = "done"
        const val ID_PROGRESS = 41
        const val ACTION_CANCEL = "io.github.snakemax.airag.CANCEL_JOBS"
        const val ACTION_STOP = "io.github.snakemax.airag.STOP_JOBS"
        const val EXTRA_TITLE = "title"
        const val EXTRA_COUNT = "count"
        const val EXTRA_LINES = "lines"
        const val EXTRA_HASH = "hash"
        @Volatile var running = false
        private var lastTitle = ""
        private var lastCount = 0
        private var lastLines = ""
        private var doneId = 100

        fun channels(ctx: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.deleteNotificationChannel("jobs")   // 0.4 test 1: low importance hid the status bar icon
            nm.createNotificationChannel(NotificationChannel(CHANNEL_PROGRESS, ctx.getString(R.string.ch_jobs),
                NotificationManager.IMPORTANCE_DEFAULT).apply {
                    setSound(null, null)            // shown in the status bar, but silent
                    enableVibration(false)
                    setShowBadge(true)
                })
            nm.createNotificationChannel(NotificationChannel(CHANNEL_DONE, ctx.getString(R.string.ch_done),
                NotificationManager.IMPORTANCE_DEFAULT))
        }

        private fun openApp(ctx: Context, hash: String, req: Int): PendingIntent {
            val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            if (hash.isNotEmpty()) i.putExtra(EXTRA_HASH, hash)
            return PendingIntent.getActivity(ctx, req, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        }

        fun progress(ctx: Context, title: String, count: Int, lines: String): Notification {
            channels(ctx)
            val cancel = PendingIntent.getService(ctx, 1, Intent(ctx, JobService::class.java).setAction(ACTION_CANCEL),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            return NotificationCompat.Builder(ctx, CHANNEL_PROGRESS)
                .setSmallIcon(R.drawable.ic_stat_airag)
                .setContentTitle(title.ifEmpty { ctx.getString(R.string.job_working) })
                .setContentText(if (count > 1) ctx.getString(R.string.job_more, count - 1) else ctx.getString(R.string.job_background))
                .setProgress(0, 0, true)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setSilent(true)
                .setCategory(NotificationCompat.CATEGORY_PROGRESS)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                // Android 12+ otherwise waits up to 10 s before showing it, so short searches never showed one
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .setContentIntent(openApp(ctx, "", 2))
                .addAction(0, ctx.getString(R.string.job_cancel), cancel)
                .apply {
                    // expanded: one line per running or queued job
                    val all = lines.split("\n").filter { it.isNotBlank() }
                    if (all.size > 1) {
                        val style = NotificationCompat.InboxStyle().setBigContentTitle(title)
                        all.forEach { style.addLine(it) }
                        setStyle(style)
                    }
                }
                .build()
        }

        /** Python reports what's running: count 0 stops the service. */
        fun update(ctx: Context, count: Int, title: String, lines: String = lastLines) {
            val app = ctx.applicationContext
            lastTitle = title
            lastCount = count
            lastLines = lines
            if (count <= 0) {
                if (running) app.startService(Intent(app, JobService::class.java).setAction(ACTION_STOP))
                return
            }
            if (running) {   // already in the foreground: just refresh the notification
                try { app.getSystemService(NotificationManager::class.java).notify(ID_PROGRESS, progress(app, title, count, lines)) } catch (_: SecurityException) { }
                return
            }
            val i = Intent(app, JobService::class.java).putExtra(EXTRA_TITLE, title).putExtra(EXTRA_COUNT, count)
                .putExtra(EXTRA_LINES, lines)
            try { ContextCompat.startForegroundService(app, i) } catch (_: Exception) { /* not allowed right now: the job still runs while the app is open */ }
        }

        /** Show the running notification again, e.g. right after the user allowed notifications. */
        fun refresh(ctx: Context) {
            if (running && lastCount > 0) update(ctx, lastCount, lastTitle)
        }

        fun done(ctx: Context, title: String, text: String, hash: String, failed: Boolean = false) {
            val app = ctx.applicationContext
            channels(app)
            val n = NotificationCompat.Builder(app, CHANNEL_DONE)
                .setSmallIcon(R.drawable.ic_stat_airag)
                .setContentTitle(if (failed) app.getString(R.string.failed_title, title) else title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .setContentIntent(openApp(app, hash, 1000 + doneId))
                .build()
            try { app.getSystemService(NotificationManager::class.java).notify(doneId++, n) } catch (_: SecurityException) { }
        }
    }
}
