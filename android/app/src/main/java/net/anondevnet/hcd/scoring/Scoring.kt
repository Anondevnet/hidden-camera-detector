package net.anondevnet.hcd.scoring

data class Reason(val code: String, val detail: String, val weight: Int)

enum class Likelihood { UNLIKELY, POSSIBLE, LIKELY, HIGHLY_LIKELY }

data class DeviceFinding(
    val ip: String?,
    val hostname: String? = null,
    val openPorts: List<Int> = emptyList(),
    val services: List<String> = emptyList(),
    val vendorName: String? = null,
    val reasons: List<Reason> = emptyList(),
    val score: Int = 0,
    val likelihood: Likelihood = Likelihood.UNLIKELY,
)

data class BleFinding(
    val address: String,
    val name: String?,
    val rssi: Int?,
    val kind: String = "unknown",
    val reasons: List<Reason> = emptyList(),
    val score: Int = 0,
    val likelihood: Likelihood = Likelihood.UNLIKELY,
)

object Scoring {
    private val cameraName = Regex(
        """hikvision|dahua|amcrest|reolink|wyze|eufy|tapo|foscam|ezviz|imou|uniview|lorex|swann|arlo|blink|onvif|ipcam|ip-?camera|security-?cam|camera|nvr|dvr|\bipc\b|cctv""",
        RegexOption.IGNORE_CASE,
    )

    private val ports = mapOf(
        554 to Reason("port-554", "TCP 554 open (RTSP, used to stream camera video)", 35),
        8554 to Reason("port-8554", "TCP 8554 open (alternate RTSP)", 20),
        37777 to Reason("port-37777", "TCP 37777 open (Dahua / Amcrest media service)", 30),
        34567 to Reason("port-34567", "TCP 34567 open (XM / Sofia / many generic IPC kits)", 30),
        8899 to Reason("port-8899", "TCP 8899 open (often ONVIF)", 15),
        8000 to Reason("port-8000", "TCP 8000 open (common vendor HTTP / SDK port)", 10),
        80 to Reason("port-80", "TCP 80 open (HTTP)", 5),
        8080 to Reason("port-8080", "TCP 8080 open (alternate HTTP)", 5),
        443 to Reason("port-443", "TCP 443 open (HTTPS)", 3),
    )

    fun likelihood(score: Int): Likelihood = when {
        score >= 70 -> Likelihood.HIGHLY_LIKELY
        score >= 40 -> Likelihood.LIKELY
        score >= 20 -> Likelihood.POSSIBLE
        else -> Likelihood.UNLIKELY
    }

    fun scoreDevice(
        ip: String?,
        hostname: String?,
        openPorts: List<Int>,
        services: List<String>,
    ): DeviceFinding {
        val reasons = mutableListOf<Reason>()
        var total = 0
        fun add(reason: Reason) {
            reasons += reason
            total += reason.weight
        }
        openPorts.distinct().forEach { port ->
            ports[port]?.let { add(it) }
        }
        services.forEach { service ->
            val lower = service.lowercase()
            when {
                "onvif" in lower -> add(Reason("onvif", "Discovered via ONVIF / mDNS / WS-Discovery ($service)", 40))
                "rtsp" in lower -> add(Reason("mdns-rtsp", "Advertised an RTSP service ($service)", 40))
                "axis-video" in lower -> add(Reason("axis-video", "Advertised an Axis video service ($service)", 40))
                "ssdp" in lower || "upnp" in lower -> add(Reason("ssdp", "SSDP / UPnP advertisement ($service)", 10))
            }
        }
        val nameBlob = listOfNotNull(hostname).plus(services).joinToString(" ")
        if (nameBlob.isNotBlank() && cameraName.containsMatchIn(nameBlob)) {
            add(Reason("name", "Hostname or service name looks camera-related: ${nameBlob.take(160)}", 20))
        }
        val score = total.coerceIn(0, 100)
        return DeviceFinding(
            ip = ip,
            hostname = hostname,
            openPorts = openPorts.distinct().sorted(),
            services = services,
            reasons = reasons,
            score = score,
            likelihood = likelihood(score),
        )
    }
}
