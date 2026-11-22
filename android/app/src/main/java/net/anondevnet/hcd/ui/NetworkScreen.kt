package net.anondevnet.hcd.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import net.anondevnet.hcd.scoring.DeviceFinding

@Composable
fun NetworkScreen(
    running: Boolean,
    progress: String,
    cidr: String?,
    note: String?,
    devices: List<DeviceFinding>,
    error: String?,
    onScan: () -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("LAN scan", style = MaterialTheme.typography.headlineSmall)
        Text(
            cidr?.let { "Subnet $it" } ?: "Uses the IPv4 subnet of the current Wi-Fi, plus mDNS and SSDP.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 6.dp, bottom = 12.dp),
        )
        Button(onClick = onScan, enabled = !running) {
            Text(if (running) "Scanning…" else "Scan this Wi-Fi")
        }
        if (running) {
            CircularProgressIndicator(Modifier.padding(top = 16.dp))
            Text(progress, modifier = Modifier.padding(top = 8.dp))
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }
        note?.let { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp)) }
        LazyColumn(Modifier.padding(top = 12.dp)) {
            items(devices) { device ->
                ListItem(
                    headlineContent = {
                        Text("${device.score}  ${device.likelihood.name.lowercase().replace('_', ' ')}  ${device.ip}")
                    },
                    supportingContent = {
                        val ports = if (device.openPorts.isEmpty()) "" else "ports ${device.openPorts.joinToString()}"
                        val host = device.hostname ?: ""
                        Text(listOf(host, ports).filter { it.isNotBlank() }.joinToString(" · ").ifBlank { "no extra signals" })
                    },
                )
            }
        }
    }
}
