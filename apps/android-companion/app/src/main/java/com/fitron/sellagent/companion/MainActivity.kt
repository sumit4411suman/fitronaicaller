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
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
import com.fitron.sellagent.companion.ui.EmergencyScreen
import com.fitron.sellagent.companion.ui.SettingsScreen
import com.fitron.sellagent.companion.ui.StatusScreen
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.PairingScreen
import com.fitron.sellagent.core.ui.PermissionsScreen

object Routes {
    const val PAIRING = "pairing"
    const val STATUS = "status"
    const val CALLS = "calls"
    const val EMERGENCY = "emergency"
    const val PERMISSIONS = "permissions"
    const val SETTINGS = "settings"
}

private data class Dest(val route: String, val label: Int, val icon: ImageVector)

private val tabs = listOf(
    Dest(Routes.STATUS, R.string.nav_status, Icons.Filled.Home),
    Dest(Routes.CALLS, R.string.nav_calls, Icons.Filled.Call),
    Dest(Routes.EMERGENCY, R.string.nav_emergency, Icons.Filled.Warning),
    Dest(Routes.PERMISSIONS, R.string.nav_permissions, Icons.Filled.Lock),
    Dest(Routes.SETTINGS, R.string.nav_settings, Icons.Filled.Settings),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { SellAgentTheme { CompanionNav() } }
    }
}

@Composable
private fun CompanionNav() {
    val navController = rememberNavController()
    val core = LocalContext.current.core()
    val pairing by core.store.pairing.collectAsStateWithLifecycle()
    val backStack by navController.currentBackStackEntryAsState()
    val currentDestination = backStack?.destination
    val pending by (LocalContext.current.applicationContext as CompanionApp).calls.pending.collectAsStateWithLifecycle()
    Scaffold(
        containerColor = BrandColors.Background,
        bottomBar = {
            NavigationBar(containerColor = BrandColors.Surface, contentColor = BrandColors.TextPrimary) {
                tabs.forEach { d ->
                    val selected = currentDestination?.hierarchy?.any { it.route == d.route } == true
                    val label = stringResource(d.label)
                    val highlight = d.route == Routes.CALLS && pending != null
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            navController.navigate(d.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(d.icon, contentDescription = label, tint = if (highlight && !selected) BrandColors.Warning else androidx.compose.ui.graphics.Color.Unspecified) },
                        label = { Text(label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = BrandColors.OnGold,
                            selectedTextColor = BrandColors.Gold,
                            indicatorColor = if (d.route == Routes.EMERGENCY) BrandColors.EmergencyStop else BrandColors.Gold,
                            unselectedIconColor = BrandColors.TextSecondary,
                            unselectedTextColor = BrandColors.TextSecondary,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            NavHost(navController = navController, startDestination = if (pairing == null) Routes.PAIRING else Routes.STATUS) {
                composable(Routes.PAIRING) { PairingScreen(appLabel = stringResource(R.string.app_short_label)) }
                composable(Routes.STATUS) { StatusScreen(onPair = { navController.navigate(Routes.PAIRING) }) }
                composable(Routes.CALLS) { CallsScreen() }
                composable(Routes.EMERGENCY) { EmergencyScreen() }
                composable(Routes.PERMISSIONS) { PermissionsScreen() }
                composable(Routes.SETTINGS) { SettingsScreen(onPair = { navController.navigate(Routes.PAIRING) }) }
            }
        }
    }
}
