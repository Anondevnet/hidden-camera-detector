package net.anondevnet.hcd.ble

import net.anondevnet.hcd.scoring.BleFinding
import net.anondevnet.hcd.scoring.Reason
import net.anondevnet.hcd.scoring.Scoring

object Signatures {
    val cameraNames = listOf(
        "wyze", "reolink", "eufy", "tapo", "hikvision", "dahua", "amcrest", "foscam",
        "ezviz", "imou", "arlo", "blink", "nest cam", "nest-cam", "ring cam",
        "ring floodlight", "ring spotlight", "lorex", "yi cam", "ipcam", "ip-cam",
        "security cam", "indoor cam", "outdoor cam",
    )
    val weakCameraNames = listOf("camera", "webcam", "cam-", "_cam")
    val trackerNames = listOf(
        "tile", "airtag", "smarttag", "smart tag", "chipolo", "eufy tag",
        "galaxy smarttag", "item finder", "tracker",
    )

    fun score(address: String, name: String?, rssi: Int?): BleFinding {
        val reasons = mutableListOf<Reason>()
        var total = 0
        var kind = "unknown"
        val text = name.orEmpty()
        if (trackerNames.any { it in text.lowercase() }) {
            reasons += Reason("ble-tracker-name", "Advertised name looks like a tracker: $name", 40)
            total += 40
            kind = "tracker"
        }
        if (cameraNames.any { it in text.lowercase() }) {
            reasons += Reason("ble-camera-name", "Advertised name matches a camera brand or product: $name", 50)
            total += 50
            kind = "camera"
        } else if (weakCameraNames.any { it in text.lowercase() } && kind != "tracker") {
            reasons += Reason("ble-name-weak", "Advertised name contains a generic 'cam' token: $name", 20)
            total += 20
            kind = "camera"
        }
        val score = total.coerceIn(0, 100)
        return BleFinding(
            address = address,
            name = name,
            rssi = rssi,
            kind = kind,
            reasons = reasons,
            score = score,
            likelihood = Scoring.likelihood(score),
        )
    }
}
