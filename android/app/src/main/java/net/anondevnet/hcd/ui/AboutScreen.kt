package net.anondevnet.hcd.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import net.anondevnet.hcd.R

@Composable
fun AboutScreen() {
    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Text(stringResource(R.string.consent_title), style = MaterialTheme.typography.headlineSmall)
        Text(
            stringResource(R.string.consent_body),
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.padding(top = 12.dp),
        )
        Text(
            "Android will not give a regular app the MAC addresses of other devices on the Wi-Fi, " +
                "so this LAN scan cannot do vendor / OUI lookup. For that, run `hcd network` from a laptop " +
                "on the same network. Optical and BLE checks run entirely on the phone.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 16.dp),
        )
        Text(
            "iOS is not shipped as a native app here. Safari can run the web UI’s camera mode over HTTPS, " +
                "but it cannot scan the LAN or Bluetooth, and it typically cannot turn on the torch.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 12.dp),
        )
    }
}
