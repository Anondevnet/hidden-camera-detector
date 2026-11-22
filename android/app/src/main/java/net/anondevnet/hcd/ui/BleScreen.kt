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
import net.anondevnet.hcd.scoring.BleFinding

@Composable
fun BleScreen(
    running: Boolean,
    devices: List<BleFinding>,
    error: String?,
    onScan: () -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Bluetooth", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Looks at advertised names for camera and tracker hints. A phone advertising an Apple or Samsung company ID is not, by itself, a finding.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 6.dp, bottom = 12.dp),
        )
        Button(onClick = onScan, enabled = !running) {
            Text(if (running) "Scanning…" else "Scan BLE")
        }
        if (running) CircularProgressIndicator(Modifier.padding(top = 16.dp))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }
        LazyColumn(Modifier.padding(top = 12.dp)) {
            items(devices) { device ->
                ListItem(
                    headlineContent = {
                        Text("${device.score}  ${device.kind}  ${device.name ?: "(no name)"}")
                    },
                    supportingContent = {
                        Text("${device.address}  rssi=${device.rssi ?: "?"}")
                    },
                )
            }
        }
    }
}
