package net.anondevnet.hcd.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.NetworkCapabilities
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import net.anondevnet.hcd.scoring.DeviceFinding
import net.anondevnet.hcd.scoring.Scoring
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.Socket

data class DiscoveredService(
    val ip: String?,
    val name: String,
    val tag: String,
)

class NetworkScanner(private val context: Context) {

    data class Result(
        val cidr: String?,
        val devices: List<DeviceFinding>,
        val note: String,
    )

    private val ports = listOf(554, 80, 8080, 8000, 37777, 34567)
    private val mdnsTypes = listOf(
        "_onvif._tcp",
        "_rtsp._tcp",
        "_axis-video._tcp",
        "_http._tcp",
    )

    suspend fun scan(onProgress: (String) -> Unit = {}): Result = withContext(Dispatchers.IO) {
        val cidr = localCidr()
        onProgress("Discovery (mDNS + SSDP)…")
        val services = discover(timeoutMs = 2_500)
        val seeds = linkedMapOf<String, MutableList<String>>()
        val hostnames = mutableMapOf<String, String>()
        services.forEach { service ->
            val ip = service.ip ?: return@forEach
            seeds.getOrPut(ip) { mutableListOf() }.add("${service.tag}:${service.name}")
            if (service.name.isNotBlank()) {
                hostnames.putIfAbsent(ip, service.name)
            }
        }
        val hosts = (hostsFromCidr(cidr) + seeds.keys).distinct()
        onProgress("Probing ${hosts.size} addresses on camera ports…")
        val open = probeAll(hosts)
        open.keys.forEach { ip -> seeds.getOrPut(ip) { mutableListOf() } }
        val devices = seeds.keys.union(open.keys).map { ip ->
            Scoring.scoreDevice(
                ip = ip,
                hostname = hostnames[ip],
                openPorts = open[ip].orEmpty(),
                services = seeds[ip].orEmpty(),
            )
        }.sortedByDescending { it.score }
        Result(
            cidr = cidr,
            devices = devices,
            note = "Android does not expose other devices’ MAC addresses to regular apps, so this scan cannot do OUI vendor lookup. Use the laptop CLI on the same Wi-Fi for that.",
        )
    }

    private fun localCidr(): String? {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return fallbackWifiCidr()
        val caps = cm.getNetworkCapabilities(network) ?: return fallbackWifiCidr()
        if (!caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) &&
            !caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
        ) {
            return fallbackWifiCidr()
        }
        val props: LinkProperties = cm.getLinkProperties(network) ?: return fallbackWifiCidr()
        val ipv4 = props.linkAddresses.firstOrNull { it.address.hostAddress?.contains(':') == false }
            ?: return fallbackWifiCidr()
        val host = ipv4.address.hostAddress ?: return fallbackWifiCidr()
        val prefix = ipv4.prefixLength
        return toCidr(host, prefix)
    }

    @Suppress("DEPRECATION")
    private fun fallbackWifiCidr(): String? {
        val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val addr = wifi.connectionInfo?.ipAddress ?: return null
        if (addr == 0) return null
        val host = String.format(
            "%d.%d.%d.%d",
            addr and 0xff,
            addr shr 8 and 0xff,
            addr shr 16 and 0xff,
            addr shr 24 and 0xff,
        )
        return toCidr(host, 24)
    }

    private fun toCidr(host: String, prefix: Int): String {
        val octets = host.split('.').map { it.toInt() }
        val raw = (octets[0] shl 24) or (octets[1] shl 16) or (octets[2] shl 8) or octets[3]
        val mask = if (prefix <= 0) 0 else (-1 shl (32 - prefix))
        val network = raw and mask
        val base = listOf(
            (network ushr 24) and 0xff,
            (network ushr 16) and 0xff,
            (network ushr 8) and 0xff,
            network and 0xff,
        ).joinToString(".")
        return "$base/$prefix"
    }

    private fun hostsFromCidr(cidr: String?): List<String> {
        if (cidr == null) return emptyList()
        val (base, prefixStr) = cidr.split("/")
        val prefix = prefixStr.toInt()
        if (prefix < 22 || prefix > 30) return emptyList()
        val octets = base.split('.').map { it.toInt() }
        val raw = (octets[0] shl 24) or (octets[1] shl 16) or (octets[2] shl 8) or octets[3]
        val count = 1 shl (32 - prefix)
        // Skip network and broadcast.
        return (1 until count - 1).map { offset ->
            val value = raw + offset
            listOf(
                (value ushr 24) and 0xff,
                (value ushr 16) and 0xff,
                (value ushr 8) and 0xff,
                value and 0xff,
            ).joinToString(".")
        }
    }

    private suspend fun probeAll(hosts: List<String>): Map<String, List<Int>> = coroutineScope {
        hosts.map { ip ->
            async {
                val open = ports.map { port ->
                    async { if (probe(ip, port, 200)) port else null }
                }.awaitAll().filterNotNull()
                ip to open
            }
        }.awaitAll().filter { it.second.isNotEmpty() }.toMap()
    }

    private fun probe(ip: String, port: Int, timeoutMs: Int): Boolean {
        return try {
            Socket().use { socket ->
                socket.connect(InetSocketAddress(ip, port), timeoutMs)
                true
            }
        } catch (_: Exception) {
            false
        }
    }

    private suspend fun discover(timeoutMs: Long): List<DiscoveredService> = coroutineScope {
        val mdns = async { mdnsBrowse(timeoutMs) }
        val ssdp = async { ssdpSearch(timeoutMs) }
        mdns.await() + ssdp.await()
    }

    private suspend fun mdnsBrowse(timeoutMs: Long): List<DiscoveredService> {
        val manager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
        val found = mutableListOf<DiscoveredService>()
        val listeners = mutableListOf<NsdManager.DiscoveryListener>()
        mdnsTypes.forEach { type ->
            val listener = object : NsdManager.DiscoveryListener {
                override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {}
                override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {}
                override fun onDiscoveryStarted(serviceType: String?) {}
                override fun onDiscoveryStopped(serviceType: String?) {}
                override fun onServiceLost(serviceInfo: NsdServiceInfo?) {}
                override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                    manager.resolveService(
                        serviceInfo,
                        object : NsdManager.ResolveListener {
                            override fun onResolveFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {}
                            override fun onServiceResolved(resolved: NsdServiceInfo) {
                                val ip = resolved.host?.hostAddress
                                val tag = when {
                                    type.contains("onvif") -> "onvif"
                                    type.contains("rtsp") -> "rtsp"
                                    type.contains("axis-video") -> "axis-video"
                                    else -> "mdns"
                                }
                                synchronized(found) {
                                    found += DiscoveredService(ip, resolved.serviceName ?: type, tag)
                                }
                            }
                        },
                    )
                }
            }
            listeners += listener
            try {
                manager.discoverServices(type, NsdManager.PROTOCOL_DNS_SD, listener)
            } catch (_: Exception) {
            }
        }
        delay(timeoutMs)
        listeners.forEach { listener ->
            try {
                manager.stopServiceDiscovery(listener)
            } catch (_: Exception) {
            }
        }
        return found.toList()
    }

    private fun ssdpSearch(timeoutMs: Long): List<DiscoveredService> {
        val payload = (
            "M-SEARCH * HTTP/1.1\r\n" +
                "HOST: 239.255.255.250:1900\r\n" +
                "MAN: \"ssdp:discover\"\r\n" +
                "MX: 2\r\n" +
                "ST: ssdp:all\r\n\r\n"
            ).toByteArray()
        val found = mutableListOf<DiscoveredService>()
        try {
            MulticastSocket().use { socket ->
                socket.soTimeout = 250
                socket.send(
                    DatagramPacket(
                        payload,
                        payload.size,
                        InetAddress.getByName("239.255.255.250"),
                        1900,
                    ),
                )
                val end = System.currentTimeMillis() + timeoutMs
                val buf = ByteArray(2048)
                while (System.currentTimeMillis() < end) {
                    try {
                        val packet = DatagramPacket(buf, buf.size)
                        socket.receive(packet)
                        val text = String(packet.data, 0, packet.length)
                        val ip = httpHost(text) ?: packet.address?.hostAddress
                        val cameraish = Regex("onvif|rtsp|camera|ipcam|hikvision|dahua|reolink", RegexOption.IGNORE_CASE)
                            .containsMatchIn(text)
                        val label = listOfNotNull(firstHeader(text, "SERVER"), firstHeader(text, "ST"), firstHeader(text, "USN")).joinToString(" ")
                        val tag = if (cameraish) "ssdp" else "ssdp"
                        found += DiscoveredService(ip, label.ifBlank { "ssdp" }, tag)
                    } catch (_: Exception) {
                    }
                }
            }
        } catch (_: Exception) {
        }
        return found
    }

    private fun httpHost(text: String): String? {
        val location = firstHeader(text, "LOCATION") ?: return null
        val match = Regex("https?://([^/:]+)").find(location) ?: return null
        return match.groupValues[1]
    }

    private fun firstHeader(text: String, name: String): String? {
        return text.lineSequence()
            .map { it.trim() }
            .firstOrNull { it.startsWith("$name:", ignoreCase = true) }
            ?.substringAfter(":")
            ?.trim()
    }
}
