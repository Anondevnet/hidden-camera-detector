package net.anondevnet.hcd.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import kotlinx.coroutines.delay
import net.anondevnet.hcd.scoring.BleFinding

class BleScanner(private val context: Context) {

    @SuppressLint("MissingPermission")
    suspend fun scan(timeoutMs: Long = 8_000): List<BleFinding> {
        val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = manager.adapter ?: throw IllegalStateException("This device has no Bluetooth adapter")
        val scanner = adapter.bluetoothLeScanner
            ?: throw IllegalStateException("Bluetooth is off or BLE scanning is unavailable")
        val found = linkedMapOf<String, BleFinding>()
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val device = result.device ?: return
                val address = device.address ?: return
                val name = result.scanRecord?.deviceName ?: device.name
                found[address] = Signatures.score(address, name, result.rssi)
            }

            override fun onBatchScanResults(results: MutableList<ScanResult>) {
                results.forEach { onScanResult(0, it) }
            }
        }
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        scanner.startScan(null, settings, callback)
        try {
            delay(timeoutMs)
        } finally {
            try {
                scanner.stopScan(callback)
            } catch (_: Exception) {
            }
        }
        return found.values.sortedByDescending { it.score }
    }
}
