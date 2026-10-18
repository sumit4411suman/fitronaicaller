package com.fitron.sellagent.audiotest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.OnboardingScreen
import com.fitron.sellagent.core.ui.SplashScreen
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.fitron.sellagent.R
import com.fitron.sellagent.audiotest.ui.CallControlScreen
import com.fitron.sellagent.audiotest.ui.ReportScreen
import com.fitron.sellagent.audiotest.ui.TestRunnerScreen
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.brand.SellAgentTheme
import com.fitron.sellagent.core.ui.PairingScreen
import com.fitron.sellagent.core.ui.AudioRouteScreen
import com.fitron.sellagent.core.ui.BatteryScreen
import com.fitron.sellagent.core.ui.CoreDest
import com.fitron.sellagent.core.ui.DiagnosticsScreen
import com.fitron.sellagent.core.ui.LogsScreen
import com.fitron.sellagent.core.ui.MicTestScreen
import com.fitron.sellagent.core.ui.SpeakerTestScreen
import com.fitron.sellagent.core.ui.TroubleshootingScreen
import com.fitron.sellagent.core.ui.PermissionsScreen

private data class Dest(val route: String, val label: Int, val icon: ImageVector)

private val destinations = listOf(
    Dest("pairing", R.string.nav_pairing, Icons.Filled.Lock),
    Dest("permissions", R.string.nav_permissions, Icons.Filled.Settings),
    Dest("tests", R.string.nav_tests, Icons.Filled.List),
    Dest("call", R.string.nav_call, Icons.Filled.Call),
    Dest("report", R.string.nav_report, Icons.Filled.Info),
)

/** Maps shared core destinations onto this app's routes. */
fun routeOf(dest: CoreDest): String = when (dest) {
    CoreDest.CONNECTION -> "pairing"
    CoreDest.PERMISSIONS -> "permissions"
    CoreDest.DIAGNOSTICS -> "diagnostics"
    CoreDest.BATTERY -> "battery"
    CoreDest.LOGS -> "logs"
    CoreDest.TROUBLESHOOTING -> "troubleshooting"
    CoreDest.MIC_TEST -> "mic_test"
    CoreDest.SPEAKER_TEST -> "speaker_test"
    CoreDest.AUDIO_ROUTE -> "audio_route"
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { DiagnosticRoot() }
    }
}

@Composable
private fun DiagnosticRoot() {
    val core = LocalContext.current.core()
    var splashDone by rememberSaveable { mutableStateOf(false) }
    val onboardingDone by core.uiPrefs.onboardingDone.collectAsStateWithLifecycle()
    when {
        !splashDone -> SplashScreen { splashDone = true }
        !onboardingDone -> SellAgentTheme { OnboardingScreen(R.string.onb_1_body) { core.uiPrefs.setOnboardingDone(true) } }
        else -> SellAgentTheme { DiagnosticNav() }
    }
}

@Composable
private fun DiagnosticNav() {
    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val currentDestination = backStack?.destination
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface, contentColor = MaterialTheme.colorScheme.onSurface) {
                destinations.forEach { d ->
                    val selected = currentDestination?.hierarchy?.any { it.route == d.route } == true
                    val label = stringResource(d.label)
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            navController.navigate(d.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(d.icon, contentDescription = label) },
                        label = { Text(label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = BrandColors.Gold,
                            selectedTextColor = BrandColors.GoldDark,
                            indicatorColor = BrandColors.ChipWarningBg,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            NavHost(navController = navController, startDestination = "pairing") {
                composable("pairing") { PairingScreen(appLabel = stringResource(R.string.app_short_label)) }
                composable("permissions") { PermissionsScreen() }
                composable("tests") { TestRunnerScreen() }
                composable("call") { CallControlScreen() }
                composable("report") { ReportScreen(navigate = { navController.navigate(routeOf(it)) }) }
                composable("diagnostics") { DiagnosticsScreen(navigate = { navController.navigate(routeOf(it)) }) }
                composable("logs") { LogsScreen() }
                composable("troubleshooting") { TroubleshootingScreen(navigate = { navController.navigate(routeOf(it)) }) }
                composable("battery") { BatteryScreen() }
                composable("mic_test") { MicTestScreen() }
                composable("speaker_test") { SpeakerTestScreen() }
                composable("audio_route") { AudioRouteScreen() }
            }
        }
    }
}
