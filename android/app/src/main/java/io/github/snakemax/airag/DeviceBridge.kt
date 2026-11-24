package io.github.snakemax.airag

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.webkit.JavascriptInterface
import org.json.JSONObject

/**
 * window.AIRAGDevice in the web page: read-only phone status for the live resource graphs
 * (battery level, charging, battery temperature). No permission needed; nothing can be changed.
 */
class DeviceBridge(private val context: Context) {
    @JavascriptInterface
    fun battery(): String {
        val o = JSONObject()
        try {
            val i: Intent? = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if (i != null) {
                val level = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                val scale = i.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
                if (level >= 0 && scale > 0) o.put("level", Math.round(level * 100f / scale))
                val temp = i.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
                if (temp != Int.MIN_VALUE) o.put("temp", temp / 10.0)
                val status = i.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                o.put("charging", status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL)
            }
        } catch (_: Exception) { /* no battery info on this device */ }
        return o.toString()
    }
}
