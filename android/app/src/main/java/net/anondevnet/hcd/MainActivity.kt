package net.anondevnet.hcd

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bluetooth
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.PhotoCamera
import androidx.compose.material.icons.outlined.Wifi
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch
import net.anondevnet.hcd.ble.BleScanner
import net.anondevnet.hcd.network.NetworkScanner
import net.anondevnet.hcd.scoring.BleFinding
import net.anondevnet.hcd.scoring.DeviceFinding
import net.anondevnet.hcd.ui.AboutScreen
import net.anondevnet.hcd.ui.BleScreen
import net.anondevnet.hcd.ui.CameraScreen
import net.anondevnet.hcd.ui.HcdTheme
import net.anondevnet.hcd.ui.NetworkScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { HcdAppRoot() }
    }
}

private enum class Tab { Camera, Network, Bluetooth, About }

@Composable
private fun HcdAppRoot() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var tab by remember { mutableStateOf(Tab.Camera) }

    var cameraGranted by remember {
        mutableStateOf(hasPermission(context, Manifest.permission.CAMERA))
    }
    var networkRunning by remember { mutableStateOf(false) }
    var networkProgress by remember { mutableStateOf("") }
    var networkCidr by remember { mutableStateOf<String?>(null) }
    var networkNote by remember { mutableStateOf<String?>(null) }
    var networkError by remember { mutableStateOf<String?>(null) }
    var networkDevices by remember { mutableStateOf<List<DeviceFinding>>(emptyList()) }

    var bleRunning by remember { mutableStateOf(false) }
    var bleError by remember { mutableStateOf<String?>(null) }
    var bleDevices by remember { mutableStateOf<List<BleFinding>>(emptyList()) }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> cameraGranted = granted }

    val networkLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { granted ->
        if (granted.values.all { it } || granted[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
            scope.launch {
                networkRunning = true
                networkError = null
                try {
                    val result = NetworkScanner(context).scan { networkProgress = it }
                    networkCidr = result.cidr
                    networkNote = result.note
                    networkDevices = result.devices
                } catch (ex: Exception) {
                    networkError = ex.message
                } finally {
                    networkRunning = false
                }
            }
        } else {
            networkError = "Location / nearby-Wi-Fi permission is needed to scan this LAN."
        }
    }

    val bleLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { granted ->
        if (granted.values.all { it }) {
            scope.launch {
                bleRunning = true
                bleError = null
                try {
                    bleDevices = BleScanner(context).scan()
                } catch (ex: Exception) {
                    bleError = ex.message
                } finally {
                    bleRunning = false
                }
            }
        } else {
            bleError = "Bluetooth permission was denied."
        }
    }

    LaunchedEffect(tab, cameraGranted) {
        if (tab == Tab.Camera && !cameraGranted) {
            cameraLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    HcdTheme {
        Scaffold(
            bottomBar = {
                NavigationBar {
                    NavigationBarItem(
                        selected = tab == Tab.Camera,
                        onClick = {
                            tab = Tab.Camera
                            if (!cameraGranted) cameraLauncher.launch(Manifest.permission.CAMERA)
                        },
                        icon = { Icon(Icons.Outlined.PhotoCamera, contentDescription = "Camera") },
                        label = { Text("Camera") },
                    )
                    NavigationBarItem(
                        selected = tab == Tab.Network,
                        onClick = { tab = Tab.Network },
                        icon = { Icon(Icons.Outlined.Wifi, contentDescription = "Network") },
                        label = { Text("Network") },
                    )
                    NavigationBarItem(
                        selected = tab == Tab.Bluetooth,
                        onClick = { tab = Tab.Bluetooth },
                        icon = { Icon(Icons.Outlined.Bluetooth, contentDescription = "Bluetooth") },
                        label = { Text("Bluetooth") },
                    )
                    NavigationBarItem(
                        selected = tab == Tab.About,
                        onClick = { tab = Tab.About },
                        icon = { Icon(Icons.Outlined.Info, contentDescription = "About") },
                        label = { Text("About") },
                    )
                }
            },
        ) { padding ->
            androidx.compose.foundation.layout.Box(Modifier.padding(padding)) {
                when (tab) {
                    Tab.Camera -> CameraScreen(enabled = cameraGranted)
                    Tab.Network -> NetworkScreen(
                        running = networkRunning,
                        progress = networkProgress,
                        cidr = networkCidr,
                        note = networkNote,
                        devices = networkDevices,
                        error = networkError,
                        onScan = { networkLauncher.launch(networkPermissions()) },
                    )
                    Tab.Bluetooth -> BleScreen(
                        running = bleRunning,
                        devices = bleDevices,
                        error = bleError,
                        onScan = { bleLauncher.launch(blePermissions()) },
                    )
                    Tab.About -> AboutScreen()
                }
            }
        }
    }
}

private fun hasPermission(context: android.content.Context, permission: String): Boolean {
    return ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
}

private fun networkPermissions(): Array<String> {
    return if (Build.VERSION.SDK_INT >= 33) {
        arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.NEARBY_WIFI_DEVICES,
        )
    } else {
        arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        )
    }
}

private fun blePermissions(): Array<String> {
    return if (Build.VERSION.SDK_INT >= 31) {
        arrayOf(
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT,
        )
    } else {
        arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.BLUETOOTH,
            Manifest.permission.BLUETOOTH_ADMIN,
        )
    }
}
