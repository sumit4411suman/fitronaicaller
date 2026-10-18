package com.fitron.sellagent.companion

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.brand.SellAgentTheme
import com.fitron.sellagent.companion.ui.CallsScreen
import com.fitron.sellagent.companion.ui.CompanionLiveCall
import com.fitron.sellagent.companion.ui.EmergencyScreen
import com.fitron.sellagent.companion.ui.HomeScreen
import com.fitron.sellagent.companion.ui.ManagedOnPcScreen
import com.fitron.sellagent.companion.ui.MoreScreen
import com.fitron.sellagent.companion.ui.SettingsScreen
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AboutScreen
import com.fitron.sellagent.core.ui.AudioRouteScreen
import com.fitron.sellagent.core.ui.BatteryScreen
import com.fitron.sellagent.core.ui.CoreDest
import com.fitron.sellagent.core.ui.LogsScreen
import com.fitron.sellagent.core.ui.MicTestScreen
import com.fitron.sellagent.core.ui.SpeakerTestScreen
import com.fitron.sellagent.core.ui.TroubleshootingScreen
import com.fitron.sellagent.core.ui.DiagnosticsScreen
import com.fitron.sellagent.core.ui.HelpScreen
import com.fitron.sellagent.core.ui.OnboardingScreen
import com.fitron.sellagent.core.ui.PairingScreen
import com.fitron.sellagent.core.ui.PermissionsScreen
import com.fitron.sellagent.core.ui.SplashScreen

object Routes {
    const val HOME = "home"
    const val CONTACTS = "contacts"
    const val CAMPAIGNS = "campaigns"
    const val CALLS = "calls"
    const val MORE = "more"
    const val CONNECTION = "connection"
    const val DIAGNOSTICS = "diagnostics"
    const val PERMISSIONS = "permissions"
    const val SETTINGS = "settings"
    const val HELP = "help"
    const val ABOUT = "about"
    const val EMERGENCY = "emergency"
    const val LIVE = "live"
    const val LOGS = "logs"
    const val TROUBLESHOOTING = "troubleshooting"
    const val BATTERY = "battery"
    const val MIC_TEST = "mic_test"
    const val SPEAKER_TEST = "speaker_test"
    const val AUDIO_ROUTE = "audio_route"

    fun of(dest: CoreDest): String = when (dest) {
        CoreDest.CONNECTION -> CONNECTION
        CoreDest.PERMISSIONS -> PERMISSIONS
        CoreDest.DIAGNOSTICS -> DIAGNOSTICS
        CoreDest.BATTERY -> BATTERY
        CoreDest.LOGS -> LOGS
        CoreDest.TROUBLESHOOTING -> TROUBLESHOOTING
        CoreDest.MIC_TEST -> MIC_TEST
        CoreDest.SPEAKER_TEST -> SPEAKER_TEST
        CoreDest.AUDIO_ROUTE -> AUDIO_ROUTE
    }
}

private data class Tab(val route: String, val label: Int, val icon: ImageVector)

private val tabs = listOf(
    Tab(Routes.HOME, R.string.nav_home, Icons.Filled.Home),
    Tab(Routes.CONTACTS, R.string.nav_contacts, Icons.Filled.Person),
    Tab(Routes.CAMPAIGNS, R.string.nav_campaigns, Icons.Filled.DateRange),
    Tab(Routes.CALLS, R.string.nav_calls, Icons.Filled.Call),
    Tab(Routes.MORE, R.string.nav_more, Icons.Filled.Menu),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { CompanionRoot() }
    }
}

@Composable
private fun CompanionRoot() {
    val core = LocalContext.current.core()
    var splashDone by rememberSaveable { mutableStateOf(false) }
    val onboardingDone by core.uiPrefs.onboardingDone.collectAsStateWithLifecycle()
    when {
        !splashDone -> SplashScreen { splashDone = true }
        !onboardingDone -> SellAgentTheme { OnboardingScreen(R.string.onb_1_body) { core.uiPrefs.setOnboardingDone(true) } }
        else -> SellAgentTheme { CompanionNav() }
    }
}

fun NavHostController.goTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}

@Composable
private fun CompanionNav() {
    val navController = rememberNavController()
    val context = LocalContext.current
    val calls = (context.applicationContext as CompanionApp).calls
    val active by calls.active.collectAsStateWithLifecycle()
    val queue by calls.queue.collectAsStateWithLifecycle()
    val backStack by navController.currentBackStackEntryAsState()
    val currentDestination = backStack?.destination
    val onLive = currentDestination?.route == Routes.LIVE

    // Show the dark live-call screen as soon as a dialed job exists; return when it ends.
    LaunchedEffect(active?.callJobId) {
        if (active != null && navController.currentDestination?.route != Routes.LIVE) navController.navigate(Routes.LIVE) { launchSingleTop = true }
        if (active == null && navController.currentDestination?.route == Routes.LIVE) navController.popBackStack()
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            if (!onLive) {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface, contentColor = MaterialTheme.colorScheme.onSurface) {
                    tabs.forEach { t ->
                        val selected = currentDestination?.hierarchy?.any { it.route == t.route } == true
                        val label = stringResource(t.label)
                        NavigationBarItem(
                            selected = selected,
                            onClick = { navController.goTab(t.route) },
                            icon = {
                                Icon(
                                    t.icon,
                                    contentDescription = if (t.route == Routes.CALLS && queue.isNotEmpty()) "$label (${queue.size})" else label,
                                    tint = if (t.route == Routes.CALLS && queue.isNotEmpty() && !selected) BrandColors.Warning else androidx.compose.ui.graphics.Color.Unspecified,
                                )
                            },
                            label = { Text(if (t.route == Routes.CALLS && queue.isNotEmpty()) "$label (${queue.size})" else label) },
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
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            NavHost(navController = navController, startDestination = Routes.HOME) {
                composable(Routes.HOME) { HomeScreen(navigate = { navController.navigate(it) }) }
                composable(Routes.CONTACTS) { ManagedOnPcScreen(R.string.contacts_title, R.string.contacts_empty) }
                composable(Routes.CAMPAIGNS) { ManagedOnPcScreen(R.string.campaigns_title, R.string.campaigns_empty) }
                composable(Routes.CALLS) { CallsScreen() }
                composable(Routes.MORE) { MoreScreen(navigate = { navController.navigate(it) }) }
                composable(Routes.CONNECTION) { PairingScreen(appLabel = stringResource(R.string.app_short_label)) }
                composable(Routes.DIAGNOSTICS) { DiagnosticsScreen(navigate = { navController.navigate(Routes.of(it)) }) }
                composable(Routes.LOGS) { LogsScreen() }
                composable(Routes.TROUBLESHOOTING) { TroubleshootingScreen(navigate = { navController.navigate(Routes.of(it)) }) }
                composable(Routes.BATTERY) { BatteryScreen() }
                composable(Routes.MIC_TEST) { MicTestScreen() }
                composable(Routes.SPEAKER_TEST) { SpeakerTestScreen() }
                composable(Routes.AUDIO_ROUTE) { AudioRouteScreen() }
                composable(Routes.PERMISSIONS) { PermissionsScreen() }
                composable(Routes.SETTINGS) { SettingsScreen(onPair = { navController.navigate(Routes.CONNECTION) }) }
                composable(Routes.HELP) { HelpScreen() }
                composable(Routes.ABOUT) { AboutScreen(R.string.onb_1_body) }
                composable(Routes.EMERGENCY) { EmergencyScreen() }
                composable(Routes.LIVE) { CompanionLiveCall(onClose = { navController.popBackStack() }) }
            }
        }
    }
}
