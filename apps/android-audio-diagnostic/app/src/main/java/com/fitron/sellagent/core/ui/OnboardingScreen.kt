package com.fitron.sellagent.core.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors

private data class Page(val icon: ImageVector, val title: Int, val body: Int)

/** Three light pages (what the app does / permissions / pairing). No account, no login: pairing is the sign-in. */
@Composable
fun OnboardingScreen(appDescription: Int, onFinished: () -> Unit) {
    val pages = listOf(
        Page(Icons.Filled.Phone, R.string.onb_1_title, appDescription),
        Page(Icons.Filled.Lock, R.string.onb_2_title, R.string.onb_2_body),
        Page(Icons.Filled.Call, R.string.onb_3_title, R.string.onb_3_body),
    )
    var index by rememberSaveable { mutableIntStateOf(0) }
    val page = pages[index]
    Column(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(24.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onFinished) { Text(stringResource(R.string.onb_skip), color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        Column(modifier = Modifier.weight(1f).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Box(modifier = Modifier.size(112.dp).background(BrandColors.ChipWarningBg, CircleShape), contentAlignment = Alignment.Center) {
                Icon(page.icon, contentDescription = null, tint = BrandColors.GoldDark, modifier = Modifier.size(56.dp))
            }
            Spacer(Modifier.height(28.dp))
            Text(stringResource(page.title), style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onBackground, textAlign = TextAlign.Center)
            Spacer(Modifier.height(12.dp))
            Text(stringResource(page.body), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        }
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.weight(1f)) {
                pages.indices.forEach { i ->
                    Box(modifier = Modifier.size(if (i == index) 18.dp else 8.dp, 8.dp).background(if (i == index) BrandColors.Gold else MaterialTheme.colorScheme.outline, CircleShape))
                }
            }
            Spacer(Modifier.width(8.dp))
            GoldButton(if (index == pages.lastIndex) stringResource(R.string.onb_get_started) else stringResource(R.string.onb_next)) {
                if (index == pages.lastIndex) onFinished() else index++
            }
        }
    }
}
