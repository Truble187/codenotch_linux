use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum Fidelity {
    Official,
    Derived,
    Manual,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum ProviderStatus {
    Ok,
    #[serde(rename_all = "camelCase")]
    Stale { since: DateTime<Utc> },
    NeedsAuth,
    AccessDenied,
    #[serde(rename_all = "camelCase")]
    Unsupported { message: String },
    #[serde(rename_all = "camelCase")]
    Error { message: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct LimitWindow {
    pub id: String,
    pub label: String,
    pub used_fraction: Option<f64>,
    pub remaining: Option<i64>,
    pub used: Option<i64>,
    pub resets_at: Option<DateTime<Utc>>,
}

impl LimitWindow {
    pub fn summary(&self) -> String {
        if let Some(frac) = self.used_fraction {
            let used = (frac * 100.0).round() as i64;
            return format!("{}% Used · {}% left", used, (100 - used).max(0));
        }
        if let Some(remaining) = self.remaining {
            return if remaining == 1 {
                "1 left".into()
            } else {
                format!("{remaining} left")
            };
        }
        if let Some(used) = self.used {
            return if used == 1 {
                "1 used".into()
            } else {
                format!("{used} used")
            };
        }
        "No reading".into()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ProviderSnapshot {
    pub id: String,
    pub display_name: String,
    pub glyph: String,
    pub fidelity: Fidelity,
    pub status: ProviderStatus,
    pub windows: Vec<LimitWindow>,
    pub headline_id: Option<String>,
}

impl ProviderSnapshot {
    pub fn headline(&self) -> Option<&LimitWindow> {
        if let Some(id) = &self.headline_id {
            self.windows.iter().find(|w| &w.id == id)
        } else {
            self.windows.first()
        }
    }

    pub fn used_fraction(&self) -> Option<f64> {
        self.headline().and_then(|w| w.used_fraction)
    }

    pub fn headline_text(&self) -> String {
        if let Some(frac) = self.used_fraction() {
            return format!("{}%", (frac * 100.0).round() as i64);
        }
        if let Some(remaining) = self.headline().and_then(|w| w.remaining) {
            return remaining.to_string();
        }
        if let Some(used) = self.headline().and_then(|w| w.used) {
            return used.to_string();
        }
        "—".into()
    }

    pub fn band_color(used_fraction: f64) -> &'static str {
        match used_fraction {
            f if f < 0.50 => "#00FF88",
            f if f < 0.70 => "#F2FF00",
            _ => "#FF3F00",
        }
    }
}

pub fn reset_copy(resets_at: DateTime<Utc>, now: DateTime<Utc>) -> String {
    let seconds = (resets_at - now).num_seconds();
    if seconds <= 0 {
        return "Resetting…".into();
    }
    let minutes = ((seconds as f64) / 60.0).round() as i64;
    if minutes < 60 {
        return format!("Resets in {} min", minutes.max(1));
    }
    let days = (resets_at.date_naive() - now.date_naive()).num_days();
    if days >= 7 {
        return format!("Resets {}", resets_at.format("%b %-d"));
    }
    format!("Resets {}", resets_at.format("%a %-I:%M %p"))
}
